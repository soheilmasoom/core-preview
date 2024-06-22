import re

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.models.phone_verification import VerificationCode
from ledger.models import AddressBook, Asset, Network, NetworkAsset
from ledger.models.asset import AssetSerializerMini
from ledger.views.wallet_view import NetworkAssetSerializer


class AddressBookCreateSerializer(serializers.ModelSerializer):
    account = serializers.CharField(read_only=True)
    asset = AssetSerializerMini(read_only=True)
    network = serializers.CharField()
    coin = serializers.CharField(write_only=True, required=False, default=None)
    deleted = serializers.BooleanField(read_only=True)
    network_info = serializers.SerializerMethodField()
    sms_code = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    totp = serializers.CharField(write_only=True, allow_null=True, allow_blank=True, required=False)

    def validate(self, attrs):
        user = self.context['request'].user
        account = user.get_account()
        name = attrs['name']
        address = attrs['address']
        network = get_object_or_404(Network, symbol=attrs['network'])
        sms_code = attrs.get('sms_code', '')
        totp = attrs.get('totp', '')

        if attrs['coin']:
            asset = get_object_or_404(Asset, symbol=attrs['coin'])
        else:
            asset = None

        if not re.match(network.address_regex, address):
            raise ValidationError('آدرس به فرمت درستی وارد نشده است.')

        if not AddressBook.is_address_used_in_24h(address):
            sms_verification_code = VerificationCode.get_by_code(sms_code, user.phone,
                                                                 VerificationCode.SCOPE_ADDRESS_BOOK,
                                                                 user)
            if not sms_verification_code:
                raise ValidationError({'sms_code': 'کد پیامک  نامعتبر است.'})

            if not user.is_2fa_valid(totp):
                raise ValidationError({'totp': 'شناسه ‌دوعاملی صحیح نمی‌باشد.'})
            sms_verification_code.set_code_used()
        return {
            'account': account,
            'network': network,
            'asset': asset,
            'name': name,
            'address': address,
            'memo': attrs.get('memo', ''),
            'whitelist': attrs.get('whitelist', False),
        }

    def get_network_info(self, address_book: AddressBook):
        coin = self.context.get('coin')

        if coin:
            network_asset = get_object_or_404(NetworkAsset, asset__symbol=coin, network=address_book.network)

            return NetworkAssetSerializer(network_asset).data

    class Meta:
        model = AddressBook
        fields = (
            'id', 'name', 'account', 'network', 'asset', 'coin', 'address', 'deleted', 'network_info', 'sms_code',
            'totp', 'whitelist', 'memo')


class AddressBookDestroySerializer(serializers.Serializer):
    sms_code = serializers.CharField(write_only=True)
    totp = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    def validate(self, data):
        user = self.context['request'].user
        sms_code = data.get('sms_code')
        verification_code = VerificationCode.get_by_code(
            sms_code, user.phone, VerificationCode.SCOPE_ADDRESS_BOOK, user
        )

        if not verification_code:
            raise ValidationError({'code': 'کد پیامک  نامعتبر است.'})
        verification_code.set_code_used()
        totp = data.get('totp')
        if not user.is_2fa_valid(totp):
            raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})
        return data


class AddressBookUpdateSerializer(serializers.ModelSerializer):
    sms_code = serializers.CharField(write_only=True)
    totp = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    SENSITIVE_UPDATE_FIELDS = ('whitelist', )

    def validate(self, data):
        sms_code = data.pop('sms_code', None)
        totp = data.pop('totp', None)

        if not data:
            raise ValidationError('داده‌ای برای به روز‌رسانی ارسال نشده است.')

        if not (set(data) <= {'whitelist', 'name'}):
            raise ValidationError('امکان به روز‌رسانی این فیلد‌ها وجود ندارد.')

        if data.get('whitelist') is True:
            user = self.context['request'].user

            verification_code = VerificationCode.get_by_code(
                sms_code, user.phone, VerificationCode.SCOPE_ADDRESS_BOOK, user
            )

            if not verification_code:
                raise ValidationError({'sms_code': 'کد پیامک  نامعتبر است.'})
            verification_code.set_code_used()

            if not user.is_2fa_valid(totp):
                raise ValidationError({'totp': 'شناسه‌ دوعاملی صحیح نمی‌باشد.'})

        return data

    class Meta:
        model = AddressBook
        fields = ('id', 'name', 'sms_code', 'totp', 'whitelist')


class AddressBookView(ModelViewSet):
    serializer_class = AddressBookCreateSerializer

    pagination_class = LimitOffsetPagination

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return AddressBookUpdateSerializer
        else:
            return AddressBookCreateSerializer

    def get_queryset(self):
        query_params = self.request.query_params
        address_books = AddressBook.objects.filter(
            deleted=False,
            account=self.request.user.get_account()
        ).order_by('-id')

        if 'coin' in query_params:
            address_books = address_books.filter(asset__symbol=query_params['coin'])

        if 'type' in query_params:
            if query_params['type'] == 'standard':
                address_books = address_books.filter(asset__isnull=False)
            elif query_params['type'] == 'universal':
                address_books = address_books.filter(asset__isnull=True)
            else:
                address_books = address_books

        return address_books

    def destroy(self, request, *args, **kwargs):
        serializer = AddressBookDestroySerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        instance = self.get_object()
        instance.deleted = True
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_context(self):
        return {
            **super(AddressBookView, self).get_serializer_context(),
            'coin': self.request.query_params.get('coin'),
        }


class AddressBookViewV2(AddressBookView):
    pagination_class = None
