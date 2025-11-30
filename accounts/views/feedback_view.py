from rest_framework import serializers
from rest_framework.generics import CreateAPIView

from accounts.models import UserFeedback


class UserFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFeedback
        fields = ('score', 'comment')


class UserFeedbackView(CreateAPIView):
    serializer_class = UserFeedbackSerializer

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user
        )
