from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, RetrieveAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import is_app
from gamify.models import Task, Achievement, UserMission, MissionJourney, MissionDigest
from ledger.models import Prize
from ledger.models.asset import AssetSerializerMini


class AchievementSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()
    achieved = serializers.SerializerMethodField()
    redeemed = serializers.SerializerMethodField()
    fake = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    voucher = serializers.SerializerMethodField()
    voucher_expiration = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = ('id', 'amount', 'asset', 'achieved', 'redeemed', 'fake', 'voucher', 'voucher_expiration', 'type')

    def get_id(self, achievement: Achievement):
        prize = self.context['prize']
        return prize and prize.id

    def get_type(self, achievement: Achievement):
        return achievement.type

    def get_asset(self, achievement: Achievement):
        prize = self.context['prize']

        if prize and (achievement.type == Achievement.NORMAL or prize.redeemed):
            return AssetSerializerMini(prize.asset).data

        if not achievement.asset:
            return None

        return AssetSerializerMini(achievement.asset).data

    def get_amount(self, achievement: Achievement):
        prize = self.context['prize']

        if prize and (achievement.type == Achievement.NORMAL or prize.redeemed):
            return prize.amount
        else:
            return achievement.amount

    def get_voucher(self, achievement: Achievement):
        prize = self.context['prize']

        if prize and (achievement.type == Achievement.NORMAL or prize.redeemed):
            return prize.voucher_expiration is not None
        elif achievement.type == Achievement.NORMAL:
            return achievement.voucher

    def get_voucher_expiration(self, achievement: Achievement):
        prize = self.context['prize']

        if prize and (achievement.type == Achievement.NORMAL or prize.redeemed):
            return prize.voucher_expiration

    def get_achieved(self, achievement: Achievement):
        user = self.context['request'].user
        return achievement.achieved(user.get_account())

    def get_redeemed(self, achievement: Achievement):
        prize = self.context['prize']
        return bool(prize) and prize.redeemed

    def get_fake(self, achievement: Achievement):
        prize = self.context['prize']
        return bool(prize) and prize.fake


class TaskSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    finished = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ('scope', 'type', 'title', 'link', 'app_link', 'description', 'level', 'progress', 'finished')

    def get_progress(self, task: Task):
        user = self.context['request'].user
        return task.get_progress_percent(user.get_account())

    def get_finished(self, task: Task):
        user = self.context['request'].user
        return task.finished(user.get_account())


class UserMissionSerializer(serializers.ModelSerializer):
    achievements = serializers.SerializerMethodField()
    tasks = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    expiration = serializers.SerializerMethodField()
    expired = serializers.SerializerMethodField()

    class Meta:
        model = UserMission
        fields = ('id', 'name', 'achievements', 'tasks', 'finished', 'expiration', 'expired')

    def get_achievements(self, user_mission: UserMission):
        user = self.context['request'].user
        prize = Prize.objects.filter(account=user.get_account(), achievement=user_mission.mission.achievement).first()

        context = {
            **self.context,
            'prize': prize
        }

        return [
            AchievementSerializer(user_mission.mission.achievement, context=context).data,
        ]

    def get_tasks(self, user_mission: UserMission):
        return TaskSerializer(user_mission.mission.task_set.all(), many=True, context=self.context).data

    def get_name(self, user_mission: UserMission):
        return user_mission.mission.name

    def get_expiration(self, user_mission: UserMission):
        return user_mission.mission.expiration

    def get_expired(self, user_mission: UserMission):
        if user_mission.mission.expiration:
            return timezone.now() > user_mission.mission.expiration
        return False


class MissionsAPIView(ListAPIView):
    serializer_class = UserMissionSerializer

    def get_queryset(self):
        queryset = UserMission.objects.filter(user=self.request.user)

        if is_app(self.request):
            queryset = queryset.filter(mission__achievement__asset__isnull=False)

        return queryset


class ActiveMissionsAPIView(RetrieveAPIView):
    serializer_class = UserMissionSerializer

    def get_object(self):
        if is_app(self.request):
            return UserMission.objects.filter(
                user=self.request.user,
                finished=False,
                mission__active=True,
                mission__achievement__asset__isnull=False
            ).first()

        return UserMission.objects.filter(user=self.request.user, finished=False, mission__active=True).order_by('id').first()

    def retrieve(self, request, *args, **kwargs):
        user_mission = self.get_object()
        resp = {}

        if user_mission:
            resp = UserMissionSerializer(user_mission, context={'request': request}).data

        return Response(resp, status=status.HTTP_200_OK)


class TotalVoucherAPIView(APIView):
    # todo: remove this api

    def get(self, request):
        account = self.request.user.get_account()
        voucher = account.get_voucher_wallet()

        voucher_amount = 0

        if voucher:
            voucher_amount = voucher.balance

        return Response({
            'voucher_usdt': voucher_amount
        })


class MissionDigestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MissionDigest
        fields = ('title', 'description')


class MissionJourneySerializer(serializers.ModelSerializer):
    digests = MissionDigestSerializer(many=True)

    def get_logo(self, asset: MissionJourney):
        return asset.logo and asset.logo.url

    class Meta:
        model = MissionJourney
        fields = ('name', 'title', 'description', 'logo', 'digests')


class MissionJourneyAPIView(RetrieveAPIView):
    serializer_class = MissionJourneySerializer

    def get_object(self):
        return get_object_or_404(MissionJourney, name=self.kwargs['name'])
