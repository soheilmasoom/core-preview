import logging

from decouple import config, Csv
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Company, TrafficSource, Referral
from accounts.models.phone_verification import VerificationCode
from accounts.throttle import BurstRateThrottle, SustainedRateThrottle
from accounts.utils.ip import get_client_ip
from accounts.utils.login import set_login_activity
from accounts.validators import mobile_number_validator, national_card_code_validator, password_validator, company_national_id_validator
from analytics.utils.yandex import send_yandex_event
from gamify.models import MissionJourney
from rest_framework_simplejwt.tokens import AccessToken
from datetime import timedelta

logger = logging.getLogger(__name__)


class InitiateSignupSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, validators=[mobile_number_validator], trim_whitespace=True)


class InitiateSignupView(APIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request):
        if settings.DEBUG_OR_TESTING_OR_STAGING:
            req_origin = request.META.get('HTTP_ORIGIN')
            print('HTTP_ORIGIN: {}'.format(req_origin))
            if req_origin in config('SIGNUP_CLOSED_DOMAINS', cast=Csv(), default=''):
                raise ValidationError('امکان ثبت‌نام وجود ندارد.')

        if request.user.is_authenticated:
            return Response({'msg': 'already logged in', 'code': 1})

        serializer = InitiateSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']

        VerificationCode.send_otp_code(phone, VerificationCode.SCOPE_VERIFY_PHONE)

        return Response({'msg': 'otp sent', 'code': 0})


class SignupSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    token = serializers.UUIDField(write_only=True, required=True)
    password = serializers.CharField(required=False, write_only=True, validators=[password_validator])
    utm = serializers.JSONField(allow_null=True, required=False, write_only=True)
    referral_code = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    promotion = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    source = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    national_code = serializers.CharField(allow_null=True, allow_blank=True, write_only=True, required=False,
                                                validators=[national_card_code_validator])
    process_id = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)
    company_national_id = serializers.CharField(allow_null=True, allow_blank=True, write_only=True,
                                                required=False, validators=[company_national_id_validator])

    @staticmethod
    def validate_referral_code(code):
        if code and not Referral.objects.filter(code=code).exists():
            raise ValidationError(_('Referral code is invalid'))
        return code

    def create(self, validated_data):
        token = validated_data.pop('token')
        otp_code = VerificationCode.get_by_token(token, VerificationCode.SCOPE_VERIFY_PHONE)
        if not otp_code:
            raise ValidationError({'token': 'توکن نامعتبر است.'})
        phone = otp_code.phone

        promotion = validated_data.get('promotion')
        if promotion not in User.PROMOTIONS:
            promotion = MissionJourney.get_default_promotion() or ''

        company_national_id = validated_data.get('company_national_id') or None

        password = None
        if validated_data.get('source') == 'widget':
            if User.objects.filter(phone=otp_code.phone).exists():
                return User.objects.get(phone=otp_code.phone)
        else:
            password = validated_data.pop('password')
            validate_password(password=password)
            if (User.objects.filter(phone=otp_code.phone).exists() or
                    (company_national_id and Company.objects.filter(national_id=company_national_id).exists())):
                raise ValidationError({'phone': 'شما قبلا در سیستم ثبت‌نام کرده‌اید. لطفا از قسمت ورود، وارد شوید.'})

        with transaction.atomic():

            user = User.objects.create_user(
                username=phone,
                phone=phone,
                promotion=promotion
            )

            if company_national_id:
                Company.objects.create(national_id=company_national_id, user=user)

            if validated_data.get('national_code'):
                user.national_code = validated_data.get('national_code')

            if config('SHOW_NINJA_TO_ALL', cast=bool, default=False):
                user.show_community = True

            user.set_password(password)
            user.save()

            if validated_data.get('referral_code'):
                account = user.get_account()
                account.referred_by = Referral.objects.get(code=validated_data['referral_code'])
                account.save()

                from gamify.utils import check_prize_achievements, Task
                check_prize_achievements(account.referred_by.owner, Task.REFERRAL)

            # otp_code.set_token_used()

        utm = validated_data.get('utm') or {}

        self.create_traffic_source(user, utm)

        self.set_missions_to_user(user)

        send_yandex_event(user, 'sign_up', {'id': user.id})

        return user

    def create_traffic_source(self, user, utm: dict):
        def clean_data(d) -> str:
            if not d:
                d = ''

            if isinstance(d, list):
                d = d[0]

            return d[:256]

        utm_source = clean_data(utm.get('utm_source'))

        if not utm_source:
            return

        utm_medium = clean_data(utm.get('utm_medium'))
        utm_campaign = clean_data(utm.get('utm_campaign'))
        utm_content = clean_data(utm.get('utm_content'))
        utm_term = clean_data(utm.get('utm_term'))
        gps_adid = clean_data(utm.get('gps_adid'))
        profile_id = clean_data(utm.get('profile_id'))

        if utm_source == 'pwa_app':
            if utm_term.startswith('gclid'):
                utm_medium = 'google_ads'
            elif 'google-play' in utm_term and 'organic' in utm_term:
                utm_medium = 'organic'
                utm_content = 'google_play'
            elif not profile_id:
                utm_medium = 'organic'
            else:
                from accounts.models import Attribution

                attribution = Attribution.objects.filter(profile_id=profile_id).order_by('created').last()

                if not attribution:
                    utm_medium = 'organic'
                else:
                    utm_medium = attribution.utm_medium
                    utm_campaign = attribution.utm_campaign
                    utm_content = attribution.utm_content

        TrafficSource.objects.create(
            user=user,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            gps_adid=gps_adid,
            yandex_profile_id=profile_id,
            ip=get_client_ip(self.context['request']),
            user_agent=self.context['request'].META.get('HTTP_USER_AGENT', '')[:256],
        )

    def set_missions_to_user(self, user):
        from gamify.models import MissionJourney, MissionTemplate, UserMission

        try:
            account = user.get_account()
            journey = MissionJourney.get_journey(account)

            missions = []
            for mission_template in MissionTemplate.objects.filter(journey=journey, active=True):
                missions.append(UserMission(user=user, mission=mission_template))

            if missions:
                UserMission.objects.bulk_create(missions)

        except Exception as e:
            logger.warning(f'Failed to set missions to user={user.id} due to={str(e)}')


class SignupView(CreateAPIView):
    permission_classes = []
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
    serializer_class = SignupSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        if self.request.data.get('source') != 'widget':
            login(self.request, user)
            try:
                set_login_activity(
                    request=self.request,
                    user=user,
                    is_sign_up=True,
                )
            except ValueError:
                logger.exception('Error in setting login activity for signup')
        else:
            access_token = AccessToken.for_user(user)
            access_token.set_exp(lifetime=timedelta(minutes=30))
            self.token = {
                'access': str(access_token),
            }

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if hasattr(self, 'token'):
            return Response(self.token, status=201)
        return response