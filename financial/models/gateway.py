import logging
from decimal import Decimal
from typing import Type, Union

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from accounting.models import VaultItem, Vault
from accounts.models import User, SystemConfig
from financial.models import BankCard, Payment, PaymentRequest
from financial.utils.admin import MultiSelectArrayField
from financial.utils.bank import BANK_INFO, get_bank_from_iban
from financial.utils.encryption import decrypt
from ledger.models import FastBuyToken
from ledger.utils.fields import DONE, get_amount_field

logger = logging.getLogger(__name__)


class GatewayFailed(Exception):
    pass


class Gateway(models.Model):
    BASE_URL = None

    TYPES = MANUAL, ZARINPAL, PAYIR, ZIBAL, JIBIT, JIBIMO, PAYSTAR, NOVINPAL = \
        'manual', 'zarinpal', 'payir', 'zibal', 'jibit', 'jibimo', 'paystar', 'novinpal'

    name = models.CharField(max_length=128)
    type = models.CharField(
        max_length=8,
        choices=[(t, t) for t in TYPES]
    )
    merchant_id = models.CharField(max_length=128, blank=True)

    active = models.BooleanField(default=False)
    active_for_staff = models.BooleanField(default=False)
    active_for_trusted = models.BooleanField(default=False)

    ipg_deposit_enable = models.BooleanField(default=True)
    pay_id_deposit_enable = models.BooleanField(default=False)
    withdraw_enable = models.BooleanField(default=False)

    min_deposit_amount = models.PositiveIntegerField(default=10000)
    max_deposit_amount = models.PositiveIntegerField(default=50000000)
    max_daily_deposit_amount = models.PositiveIntegerField(default=100000000)

    max_auto_withdraw_amount = models.PositiveIntegerField(null=True, blank=True)
    expected_withdraw_datetime = models.DateTimeField(null=True, blank=True)

    withdraw_api_key_encrypted = models.CharField(max_length=1024, blank=True)
    withdraw_api_secret_encrypted = models.CharField(max_length=4096, blank=True)
    withdraw_api_password_encrypted = models.CharField(max_length=4096, blank=True)
    withdraw_refresh_token_encrypted = models.CharField(max_length=4096, blank=True)

    deposit_api_key = models.CharField(max_length=1024, blank=True)
    deposit_api_secret_encrypted = models.CharField(max_length=4096, blank=True)

    payment_id_api_key = models.CharField(max_length=1024, blank=True)
    payment_id_secret_encrypted = models.CharField(max_length=4096, blank=True)

    wallet_id = models.CharField(blank=True, max_length=256)

    deposit_priority = models.SmallIntegerField(default=1)
    withdraw_priority = models.SmallIntegerField(default=1)

    ipg_fee_min = models.SmallIntegerField(default=120)
    ipg_fee_max = models.SmallIntegerField(default=4000)
    ipg_fee_percent = get_amount_field(default=Decimal('0.02'))

    batch_id = models.CharField(max_length=20, null=True, blank=True)

    suspended = models.BooleanField(default=False)

    instant_withdraw_banks = MultiSelectArrayField(
        base_field=models.CharField(choices=[(bank.slug, bank.slug) for bank in BANK_INFO], max_length=16),
        default=list(),
        blank=True,
    )

    @property
    def withdraw_api_secret(self):
        return decrypt(self.withdraw_api_secret_encrypted)

    @property
    def withdraw_api_key(self):
        return decrypt(self.withdraw_api_key_encrypted)

    @property
    def withdraw_api_password(self):
        return decrypt(self.withdraw_api_password_encrypted)

    @property
    def withdraw_refresh_token(self):
        return decrypt(self.withdraw_refresh_token_encrypted)

    @property
    def deposit_api_secret(self):
        return decrypt(self.deposit_api_secret_encrypted)

    @property
    def payment_id_secret(self):
        return decrypt(self.payment_id_secret_encrypted)

    def get_balance(self) -> Union[Decimal, None]:
        v = VaultItem.objects.filter(vault__type=Vault.GATEWAY, vault__key=self.id).first()
        return v and v.balance

    def get_free(self) -> Union[Decimal, None]:
        v = VaultItem.objects.filter(vault__type=Vault.GATEWAY, vault__key=self.id).first()
        return v and v.free

    @classmethod
    def get_withdraw_fee(cls, amount):
        config = SystemConfig.get_system_config()
        return max(min(amount * config.withdraw_fee_percent // 100, config.withdraw_fee_max),
                   config.withdraw_fee_min)

    @classmethod
    def _find_best_deposit_gateway(cls, user: User, amount: Decimal = 0) -> 'Gateway':
        if user.is_staff:
            gateway = Gateway.objects.filter(active_for_staff=True, ipg_deposit_enable=True).order_by('id').first()

            if gateway:
                return gateway

        trusted_gateway = Gateway.objects.filter(active_for_trusted=True, ipg_deposit_enable=True).order_by('id').first()

        if trusted_gateway:
            payments = user.payment_set.filter(status=DONE)

            if payments.count() >= 2 and (payments.aggregate(sum=Sum('amount'))['sum'] or 0) >= 10_000_000:
                return trusted_gateway

        gateways = Gateway.objects.filter(active=True, ipg_deposit_enable=True).order_by('-deposit_priority')

        gateway = gateways.first()

        if gateways.count() <= 1:
            return gateway

        today = timezone.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

        today_payments = dict(Payment.objects.filter(
            paymentrequest__isnull=False,
            user=user,
            created__gte=today,
            status=DONE
        ).values('paymentrequest__gateway').annotate(
            total=Sum('amount')
        ).values_list('paymentrequest__gateway', 'total'))

        for g in gateways:
            if amount + today_payments.get(g.id, 0) <= g.max_daily_deposit_amount:
                return g

        return gateway

    @classmethod
    def get_active_deposit(cls, user: User, amount: Decimal = 0) -> 'Gateway':
        gateway = cls._find_best_deposit_gateway(user, amount)

        if gateway:
            return gateway.get_concrete_gateway()

    @classmethod
    def get_active_withdraw(cls, iban: str, amount: int) -> Union['Gateway', None]:
        gateways = list(Gateway.objects.filter(active=True, withdraw_enable=True).order_by('-withdraw_priority', 'id'))

        if not gateways:
            return None

        elif len(gateways) == 1:
            return gateways[0]

        with_balance_gateways = [g for g in gateways if (g.get_free() or 0) >= amount]

        if not with_balance_gateways:
            return gateways[0]

        elif len(with_balance_gateways) == 1:
            return with_balance_gateways[0]

        bank = get_bank_from_iban(iban).slug

        for g in with_balance_gateways:
            if bank in g.instant_withdraw_banks:
                return g
        else:
            return with_balance_gateways[0]

    @classmethod
    def get_active_pay_id_deposit(cls) -> 'Gateway':
        return Gateway.objects.filter(active=True, pay_id_deposit_enable=True).exclude(payment_id_api_key='').order_by('id').first()

    @classmethod
    def get_gateway_class(cls, type: str) -> Type['Gateway']:
        from financial.models import ZarinpalGateway, PaydotirGateway, ZibalGateway, JibitGateway, PaystarGateway, \
            NovinpalGateway

        mapping = {
            cls.ZARINPAL: ZarinpalGateway,
            cls.PAYIR: PaydotirGateway,
            cls.ZIBAL: ZibalGateway,
            cls.JIBIT: JibitGateway,
            # cls.JIBIMO: JibimoGateway,
            cls.PAYSTAR: PaystarGateway,
            cls.NOVINPAL: NovinpalGateway,
        }

        return mapping.get(type)

    def get_concrete_gateway(self) -> 'Gateway':
        self.__class__ = self.get_gateway_class(self.type)
        return self

    def get_initial_redirect_url(self, payment_request: PaymentRequest):
        return self.get_payment_url(payment_request)

    @classmethod
    def get_payment_url(cls, payment_request: PaymentRequest):
        raise NotImplementedError

    def create_payment_request(self, bank_card: BankCard, amount: int, source: str) -> PaymentRequest:
        raise NotImplementedError

    def verify(self, payment: Payment, **kwargs):
        self._verify(payment=payment, **kwargs)

        fast_buy_token = FastBuyToken.objects.filter(payment_request=payment.paymentrequest).last()

        if fast_buy_token:
            fast_buy_token.create_otc_for_fast_buy_token(payment)

    def _verify(self, payment: Payment, **kwargs):
        raise NotImplementedError

    def get_ipg_fee(self, amount: int) -> int:
        return max(min(int(amount * self.ipg_fee_percent / 100), self.ipg_fee_max), self.ipg_fee_min)

    def __str__(self):
        return '%s (%s)' % (self.name, self.id)
