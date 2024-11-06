from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models.firebase_token import FirebaseToken
from accounts.utils.fcm_topic import fcm_topic_manager
from accounts.utils.ip import get_client_ip
from accounts.utils.price_alert import subscribe_token_to_alert, unsubscribe_token_to_alert
from ledger.models import AssetAlert


class FirebaseTokenSerializer(serializers.ModelSerializer):
    source = serializers.CharField(allow_null=True, required=False, write_only=True, allow_blank=True)

    class Meta:
        model = FirebaseToken
        fields = ('token', 'user_agent', 'ip', 'source')


class FirebaseTokenView(APIView):
    permission_classes = []

    def post(self, request):

        user = self.request.user
        if user.is_anonymous:
            user = None
        request.data['ip'] = get_client_ip(request)
        request.data['user_agent'] = request.META['HTTP_USER_AGENT']
        serializer = FirebaseTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        user_agent = serializer.validated_data['user_agent']
        ip = serializer.validated_data['ip']
        firebase_token = FirebaseToken.objects.filter(token=token).first()

        if firebase_token:
            if user and firebase_token.user != user:
                unsubscribe_token_to_alert(firebase_token)
                FirebaseToken.objects.filter(token=token).update(user=user, user_agent=user_agent, ip=ip)

                firebase_token.refresh_from_db()
                subscribe_token_to_alert(firebase_token)
                return Response({'msg': 'token updated'})
            else:
                return Response({'msg': 'change user of token impossible'})
        else:
            firebase_token = FirebaseToken.objects.create(
                token=token,
                user=user,
                ip=ip,
                user_agent=user_agent,
                native_app=serializer.validated_data.get('source') == 'app'
            )

            subscribe_token_to_alert(firebase_token)

            return Response({'msg': 'token create'})
