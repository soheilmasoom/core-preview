from django.db import transaction
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404, CreateAPIView
from rest_framework.response import Response

from accounts.authentication import CustomTokenAuthentication
from accounts.models import SmsNotification, User, Notification, EmailNotification
from gamify.models import UserMission

SMS, EMAIL, PUSH, MISSION = 'sms', 'email', 'push', 'mission'


class NotifySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    type = serializers.ChoiceField(
        write_only=True,
        choices=[
            (SMS, SMS),
            (PUSH, PUSH),
            (EMAIL, EMAIL),
            (MISSION, MISSION)
        ])
    content = serializers.CharField(required=False, write_only=True, allow_blank=True)
    content_html = serializers.CharField(required=False, write_only=True, allow_blank=True)
    title = serializers.CharField(required=False, write_only=True, allow_blank=True)
    link = serializers.CharField(required=False, allow_blank=True, write_only=True)
    hidden = serializers.BooleanField(required=False, default=False, write_only=True)
    group_id = serializers.UUIDField(write_only=True)
    mission_template_id = serializers.IntegerField(required=False, write_only=True, allow_null=True)

    def validate(self, attrs):
        _type = attrs['type']
        title = attrs.get('title', '')
        content = attrs.get('content', '')
        content_html = attrs.get('content_html', '')

        if _type == SMS:
            if not content:
                raise serializers.ValidationError('Content should exists')

        elif _type == PUSH:
            if not title or not content:
                raise serializers.ValidationError('one of the content or (template, param) should has value')

        elif _type == EMAIL:
            if not content or not content_html:
                raise serializers.ValidationError('content_html, content should has value')

        elif _type == MISSION:
            if not attrs.get('mission_template_id'):
                raise serializers.ValidationError('mission_template_id, mission_template_id should has value')

        return attrs

    def create(self, validated_data):
        notif_type = validated_data['type']
        recipient = get_object_or_404(User.objects.filter(id=validated_data['user_id']))

        title = validated_data.get('title', '')
        content = validated_data.get('content', '')
        content_html = validated_data.get('content_html', '')
        link = validated_data.get('link', '')

        if notif_type == SMS:
            notif, created = SmsNotification.objects.get_or_create(
                recipient=recipient,
                group_id=validated_data['group_id'],
                defaults={
                    'content': content,
                }
            )

        elif notif_type == PUSH:
            notif, created = Notification.objects.get_or_create(
                recipient=recipient,
                group_id=validated_data['group_id'],
                defaults={
                    'title': title,
                    'link': link,
                    'message': content,
                    'hidden': validated_data['hidden'],
                    'push_status': Notification.PUSH_WAITING,
                    'source': 'crm'
                }
            )

        elif notif_type == EMAIL:
            notif, created = EmailNotification.objects.get_or_create(
                recipient=recipient,
                group_id=validated_data['group_id'],
                defaults={
                    'title': title,
                    'content': content,
                    'content_html': content_html,
                }
            )
        elif notif_type == MISSION:
            notif, created = UserMission.objects.get_or_create(
                user=recipient,
                mission_id=int(validated_data['mission_template_id']),
            )
        else:
            raise NotImplementedError

        return notif


class NotifyView(CreateAPIView):
    authentication_classes = [CustomTokenAuthentication]
    serializer_class = NotifySerializer

    def create(self, request, *args, **kwargs):
        if not request.user.has_perm('accounts.can_generate_notification'):
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Check if data is a list (bulk data)
        if isinstance(request.data, list):
            # Start a transaction to handle multiple creates
            try:
                with transaction.atomic():
                    serializer_list = [self.get_serializer(data=item) for item in request.data]

                    # Validate each serializer
                    for serializer in serializer_list:
                        serializer.is_valid(raise_exception=True)

                    # Save each validated serializer
                    for serializer in serializer_list:
                        serializer.save()

                    # Return a list of the created objects
                    return Response([serializer.data for serializer in serializer_list], status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return super(NotifyView, self).create(request, *args, **kwargs)
