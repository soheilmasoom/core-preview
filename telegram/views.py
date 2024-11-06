from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import TelegramLinkSerializer
from rest_framework import status
from django.shortcuts import get_object_or_404
from decouple import config
from rest_framework.authentication import BaseAuthentication
import jwt
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import exceptions, status
from rest_framework_simplejwt.tokens import AccessToken
from accounts.permissions import HasApiAccessPermission
from accounts.authentication import TelegramJWTAuthentication, InitTelegramJWTAuthentication
from .utils.redis import get_user_key, delete_user_key


User = get_user_model()

class GenerateTelegramLinkAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = TelegramLinkSerializer(context={'user': user})
        link = serializer.get_telegram_link(None)
        return Response(link)


class GetUserId(APIView):
    authentication_classes = []
    permission_classes = []
    def get(self, request):
        random_string = request.data.get("random_string")
        if not random_string:
            return Response({"error": "Random string not provided"}, status=status.HTTP_400_BAD_REQUEST)

        user_id = get_user_key(random_string)

        if user_id:
            user_id = user_id.decode("utf-8")

            # delete_user_key(random_string)

            return Response({"user_id": user_id}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid or expired link"}, status=status.HTTP_404_NOT_FOUND)


class GetUserInfoView(APIView):
    authentication_classes = [TelegramJWTAuthentication]
    permission_classes = [HasApiAccessPermission]

    api_name = 'telegram_get_user_info'

    def get(self, request, user_id):

        print("as you can see we are doing the job")
        user = get_object_or_404(User, id=user_id)
        print(user)
        user_data = {
            "id": user.phone,
            "nlu": '5000 $',
            "birth_date": user.birth_date,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "national_code": user.national_code,
        }
        return Response(user_data, status=status.HTTP_200_OK)


class GetToken(APIView):
    authentication_classes = [InitTelegramJWTAuthentication]
    permission_classes = []
    def get(self, request):
        if request.auth:
            token = str(request.auth)
            return Response({'message': 'Access granted to secure API!', 'token': token}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'No token found'}, status=status.HTTP_401_UNAUTHORIZED)
