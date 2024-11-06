from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.authentication import CustomJWTAuthentication, TelegramJWTAuthentication
from accounts.models import Account
from ledger.models.asset import CoinField


class BookmarkAssetsSerializer(serializers.ModelSerializer):
    ACTIONS = ADD, REMOVE = 'add', 'remove'

    coin = CoinField(source='asset', write_only=True)
    action = serializers.ChoiceField(choices=[(a, a) for a in ACTIONS], write_only=True)

    def update(self, instance, validated_data):
        asset = validated_data['asset']
        action = validated_data.get('action')

        if action == self.ADD:
            instance.bookmark_assets.add(asset)
        elif action == self.REMOVE:
            instance.bookmark_assets.remove(asset)
        else:
            raise NotImplementedError

        return instance

    class Meta:
        model = Account
        fields = ['coin', 'action']


class BookmarkAssetsViewSet(ModelViewSet):
    serializer_class = BookmarkAssetsSerializer
    authentication_classes = [SessionAuthentication, CustomJWTAuthentication, TelegramJWTAuthentication]

    def list(self, request, *args, **kwargs):
        account = self.request.user.get_account()

        return Response({
            'coins': list(account.bookmark_assets.values_list('symbol', flat=True))
        })

    def get_object(self):
        return self.request.user.get_account()
