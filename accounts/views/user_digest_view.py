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
    print("ok we come here 1")
    authentication_classes = [CustomTokenAuthentication]
    print("ok we come here 2")
    queryset = User.objects.all()
    print("ok we come here 3")
    serializer_class = UserSerializer
    print("ok we come here 4")
