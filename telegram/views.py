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


CUSTOM_JWT_SECRET_KEY = config('CUSTOM_JWT_SECRET_KEY')
User = get_user_model()  # Get the user model
class GenerateTelegramLinkAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print(request.user.get_account())
        print("here we go user: ", user.id)
        print("As we can see: ", user.phone)
        serializer = TelegramLinkSerializer(context={'user': user})
        print('this is the serializer data: ', serializer.data)
        link = serializer.get_telegram_link(None)
        print("this is the link: ", link)
        return Response(link)
        # return Response(serializer.data)

class GetUserInfoView(APIView):
    authentication_classes = [TelegramJWTAuthentication]
    permission_classes = [HasApiAccessPermission]

    api_name = 'telegram_get_user_info'

    def get(self, request, user_id):

        print("as you can see we are doing the job")
        # Retrieve and return the user information if token is valid
        user = get_object_or_404(User, id=user_id)
        print(user)
        user_data = {
            "id": user.phone,
            "nlu": '5000 $',
            "birth_date": user.birth_date,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "national_code": user.national_code,
            # "email": user.email,
            # "first_name": user.first_name,
            # "last_name": user.last_name,
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

#
# class get(CreateAPIView):
#     authentication_classes = (SetPasswordJWTAuthentication,)
#     throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
#     serializer_class = SetPasswordSerializer