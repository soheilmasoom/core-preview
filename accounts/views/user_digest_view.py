from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView

from accounts.authentication import CustomTokenAuthentication
from accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name')
        ref_name = "User Digest"


class UserDigestView(RetrieveAPIView):
    authentication_classes = [CustomTokenAuthentication]
    queryset = User.objects.all()
    serializer_class = UserSerializer
