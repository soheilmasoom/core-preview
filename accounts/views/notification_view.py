from django.contrib.auth.mixins import UserPassesTestMixin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.authentication import CustomTokenAuthentication
from accounts.models import UserFeedback
from accounts.models.notification import Notification
from accounts.utils.validation import parse_positive_int


class NotificationSerializer(serializers.ModelSerializer):

    def update(self, instance: Notification, validated_data):
        if 'read' in validated_data and instance.read and not validated_data['read']:
            raise ValidationError({
                'read': 'نمی‌توانید نوتیف خوانده شده را برگردانید.'
            })

        return super(NotificationSerializer, self).update(instance, validated_data)

    class Meta:
        model = Notification
        fields = ('id', 'created', 'title', 'link', 'message', 'level', 'read')
        read_only_fields = ('id', 'created', 'title', 'link', 'message', 'level')


class NotificationViewSet(ModelViewSet):
    serializer_class = NotificationSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        user = self.request.user
        feedback = user.account.trade_volume_irt and not UserFeedback.objects.filter(user=user).exists()
        only_count = request.query_params.get('only_count', default=False)
        unread_count = Notification.objects.filter(
            recipient=self.request.user,
            read=False,
            hidden=False
        ).count()
        if only_count == "1":
            return Response({
                'unread_count': unread_count,
                'feedback': feedback
            })
        else:
            return Response({
                'notifications': serializer.data,
                'unread_count': unread_count,
                'feedback': feedback
            })

    def get_queryset(self):
        notifications = Notification.objects.filter(
            recipient=self.request.user,
            hidden=False
        ).order_by('-created')

        if self.action == 'list':
            query_params = self.request.query_params
            limit = parse_positive_int(query_params.get('limit'), default=20)
            offset = parse_positive_int(query_params.get('offset'), default=0)

            return notifications[offset:limit + offset]

        return notifications


class ReadAllNotificationView(APIView):
    def patch(self, request):
        read = request.data.get('read')

        if read is not None:
            Notification.objects.filter(recipient=request.user).update(read=True)

        return Response('ok')


class NotificationViewSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        notification = Notification.send(
            **validated_data
        )
        return notification

    class Meta:
        model = Notification
        fields = ['source', 'title', 'link', 'message', 'image', 'level', 'count', 'type', 'group_id', 'recipient', 'template']
        validators = []


class NotificationView(CreateAPIView, UserPassesTestMixin):
    authentication_classes = [CustomTokenAuthentication]
    serializer_class = NotificationViewSerializer

    def test_func(self):
        permission_check = self.request.user.has_perm('accounts.can_generate_notification')
        return permission_check
