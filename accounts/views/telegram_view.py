from datetime import timedelta

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CustomTokenAuthentication, TelegramAccessToken
from accounts.models import User
from accounts.utils.telegram_auth_token import TelegramAuthKey


class GenerateTelegramLinkAPIView(APIView):
    def post(self, request):
        user = request.user
        link = TelegramAuthKey.generate_new_start_link(user)

        return Response({
            'id': user.id,
            'link': link
        })


class TelegramUserView(APIView):
    authentication_classes = [CustomTokenAuthentication]

    def get(self, request):
        auth_key = request.data.get("auth_key")

        if not auth_key:
            raise ValidationError("No user found!")

        user = TelegramAuthKey.get_user(auth_key)

        if not user:
            raise ValidationError("No user found!")

        return Response({"id": user.id})

    def patch(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            raise ValidationError("Valid user id is required!")

        user = get_object_or_404(User, id=user_id)

        telegram_notif_enable = request.query_params.get('telegram_notif_enable')

        if telegram_notif_enable not in ('0', '1'):
            raise ValidationError("No action to do!")

        user.send_notifs_to_telegram_bot = telegram_notif_enable == '1'
        user.save(update_fields=['send_notifs_to_telegram_bot'])

        return Response("done")


class GenerateTelegramAccessTokenView(APIView):
    authentication_classes = [CustomTokenAuthentication]

    def get(self, request):
        if not request.user.has_perm('accounts.can_generate_telegram_jwt_token'):
            return Response(status=status.HTTP_403_FORBIDDEN)

        user_id = request.query_params.get('user_id')
        if not user_id:
            raise ValidationError("No user provided!")

        user = get_object_or_404(User, id=user_id)

        access_token = TelegramAccessToken.for_user(user)
        access_token.set_exp(lifetime=timedelta(minutes=60))

        return Response({'access_token': str(access_token)})
