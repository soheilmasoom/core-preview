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


class CustJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        # user = request.user
        # print('the phone is', user.phone)
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, CUSTOM_JWT_SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
            # user = User.objects.get(id=user_id)
            # print("ttttttttttttttttt: ", user.phone)
            try:
                print("we arrrrrrrrrrre here")
                user = User.objects.get(id='1')
                print(user)
            except User.DoesNotExist:
                # If the user does not exist, raise an AuthenticationFailed error
                raise AuthenticationFailed("User not found")
            token = AccessToken.for_user(user)

            # Define allowed APIs for the user (you may want to customize this based on user permissions)
            token['allowed_apis'] = ['api1', 'api2']  # This is the custom claim with restricted API access

            return Response({'token': str(token)}, status=status.HTTP_200_OK)
            # return (user, token)

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token")

class GetUserInfoView(APIView):
    authentication_classes = [TelegramJWTAuthentication]
    permission_classes = [HasApiAccessPermission]

    api_name = 'telegram_get_user_info'

    def get(self, request, user_id):

        print("as you can see we are doing the job")
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response({"error": "Authorization header missing or malformed"}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, CUSTOM_JWT_SECRET_KEY, algorithms=["HS256"])

            if str(payload.get("user_id")) != str(user_id):
                return Response({"error": "User ID mismatch"}, status=status.HTTP_403_FORBIDDEN)

        except jwt.ExpiredSignatureError:
            return Response({"error": "Token has expired"}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)

        # Retrieve and return the user information if token is valid
        # user = get_object_or_404(User, id=user_id)
        # user = self.context.get('user')
        user_data = {
            "id": request.user.phone,
            "nlu": '5000 $',
            "birth_date": request.user.birth_date,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "national_code": request.user.national_code,
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
            token = str(request.auth)  # Convert token to string to return in JSON
            return Response({'message': 'Access granted to secure API!', 'token': token}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'No token found'}, status=status.HTTP_401_UNAUTHORIZED)

#
# class get(CreateAPIView):
#     authentication_classes = (SetPasswordJWTAuthentication,)
#     throttle_classes = [BurstRateThrottle, SustainedRateThrottle]
#     serializer_class = SetPasswordSerializer