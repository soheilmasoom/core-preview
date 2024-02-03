import uuid
from decimal import Decimal

from decouple import config
from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from accounts.models import Account, EmailNotification
from accounts.models import Notification
from accounts.utils.admin import url_to_edit_object
from accounts.utils.telegram import send_system_message
from analytics.event.producer import get_kafka_producer
from analytics.utils.dto import TransferEvent
from ledger.models import Trx, Asset
from ledger.utils.fields import DONE, REFUND, INIT
from ledger.utils.fields import get_group_id_field, get_status_field
from ledger.utils.fraud import verify_fiat_deposit
from ledger.utils.precision import humanize_number, get_presentation_amount
from ledger.utils.price import get_last_price, USDT_IRT
from ledger.utils.wallet_pipeline import WalletPipeline


class PaymentRequest(models.Model):

    APP, DESKTOP = 'app', 'desktop'
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    gateway = models.ForeignKey('financial.Gateway', on_delete=models.PROTECT)
    bank_card = models.ForeignKey('financial.BankCard', on_delete=models.PROTECT)
    amount = models.PositiveIntegerField()
    fee = models.PositiveIntegerField()

    source = models.CharField(max_length=16, choices=((APP, APP), (DESKTOP, DESKTOP)), default=DESKTOP)

    authority = models.CharField(max_length=64, blank=True, db_index=True, null=True)
    token = models.CharField(max_length=256, blank=True)

    login_activity = models.ForeignKey('accounts.LoginActivity', on_delete=models.SET_NULL, null=True, blank=True)

    group_id = get_group_id_field()
    payment = models.OneToOneField('financial.Payment', null=True, blank=True, on_delete=models.SET_NULL)

    def get_gateway(self):
        return self.gateway.get_concrete_gateway()

    @property
    def rial_amount(self):
        return (self.fee + self.amount) * 10

    def get_or_create_payment(self):
        with transaction.atomic():
            payment, created = Payment.objects.get_or_create(
                group_id=self.group_id,
                defaults={
                    'user': self.bank_card.user,
                    'amount': self.amount,
                    'fee': self.fee
                }
            )
            if created:
                self.payment = payment
                self.save(update_fields=['payment'])

        return payment

    class Meta:
        unique_together = [('authority', 'gateway')]

    def __str__(self):
        return '%s %s' % (self.gateway, self.bank_card)


class Payment(models.Model):
    SUCCESS_URL = '/checkout/success'
    FAIL_URL = '/checkout/fail'
    SUCCESS_PAYMENT_FAIL_FAST_BUY = '/checkout/fail_trade'

    DESCRIPTION_SIZE = 256

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True)

    group_id = get_group_id_field(default=None, unique=True)

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)

    amount = models.PositiveBigIntegerField()
    fee = models.PositiveIntegerField()

    status = get_status_field()

    ref_id = models.CharField(null=True, blank=True, max_length=256)
    ref_status = models.SmallIntegerField(null=True, blank=True)

    description = models.CharField(max_length=DESCRIPTION_SIZE, blank=True)

    def __str__(self):
        return f'{humanize_number(self.amount)} IRT to {self.user}'

    def alert_payment(self):
        user = self.user
        title = 'واریز وجه با موفقیت انجام شد'
        payment_amount = humanize_number(get_presentation_amount(Decimal(self.amount)))
        description = 'مبلغ {} تومان به حساب شما واریز شد.'.format(payment_amount)

        Notification.send(
            recipient=user,
            title=title,
            message=description,
            level=Notification.SUCCESS
        )

        EmailNotification.send_by_template(
            recipient=user,
            template='fiat_deposit_successful',
            context={
                'payment_amount': payment_amount,
                'brand': settings.BRAND,
                'panel_url': settings.PANEL_URL,
                'logo_elastic_url': config('LOGO_ELASTIC_URL', ''),
            }
        )

    def accept(self, pipeline: WalletPipeline, ref_id: int = None, system_verify: bool = True):
        if system_verify and not verify_fiat_deposit(self):
            send_system_message("Verify deposit: %s" % self, link=url_to_edit_object(self))

            self.status = INIT
            self.ref_id = ref_id
            self.save(update_fields=['status', 'ref_id'])
            return

        asset = Asset.get(Asset.IRT)
        user = self.user
        account = user.get_account()

        pipeline.new_trx(
            sender=asset.get_wallet(Account.out()),
            receiver=asset.get_wallet(account),
            amount=self.amount,
            scope=Trx.TRANSFER,
            group_id=self.group_id,
        )

        self.status = DONE
        self.ref_id = ref_id
        self.save(update_fields=['status', 'ref_id'])

        if not user.first_fiat_deposit_date:
            user.first_fiat_deposit_date = timezone.now()
            user.save(update_fields=['first_fiat_deposit_date'])

        from gamify.utils import check_prize_achievements, Task
        check_prize_achievements(account, Task.DEPOSIT)

        self.alert_payment()

    def refund(self):
        with WalletPipeline() as pipeline:
            payment = Payment.objects.select_for_update().get(id=self.id)
            if payment.status != DONE:
                return

            for trx in Trx.objects.filter(group_id=payment.group_id):
                trx.revert(pipeline)

            payment.status = REFUND
            payment.save(update_fields=['status'])

    def get_redirect_url(self) -> str:
        from ledger.models import FastBuyToken

        source = self.paymentrequest.source
        desktop = PaymentRequest.DESKTOP
        fast_by_token = FastBuyToken.objects.filter(payment_request=self.paymentrequest).last()

        if source == desktop:
            if self.status == DONE:
                if fast_by_token and fast_by_token.status != FastBuyToken.DONE:
                    return settings.PANEL_URL + self.SUCCESS_PAYMENT_FAIL_FAST_BUY
                else:
                    return settings.PANEL_URL + self.SUCCESS_URL
            else:
                return settings.PANEL_URL + self.FAIL_URL
        else:
            if self.status == DONE:
                if fast_by_token and fast_by_token.status != FastBuyToken.DONE:
                    return 'intent://Checkout/success/#Intent;scheme=raastin;package=com.raastin.pro;end'
                else:
                    return 'intent://Checkout/success/#Intent;scheme=raastin;package=com.raastin.pro;end'
            else:
                return 'intent://Checkout/fail/#Intent;scheme=raastin;package=com.raastin.pro;end'

    def redirect_to_app(self):
        url = self.get_redirect_url()

        if url.startswith('http'):
            return redirect(url)
        else:
            response = HttpResponse("", status=302)
            response['Location'] = url
            return response

    class Meta:
        constraints = [
        ]


@receiver(post_save, sender=Payment)
def handle_payment_save(sender, instance, created, **kwargs):
    if instance.status != DONE or settings.DEBUG_OR_TESTING_OR_STAGING:
        return

    usdt_price = get_last_price(USDT_IRT)

    event = TransferEvent(
        id=instance.id,
        user_id=instance.user.id,
        amount=instance.amount,
        coin='IRT',
        network='IRT',
        is_deposit=True,
        value_usdt=float(instance.amount) / float(usdt_price),
        value_irt=instance.amount,
        created=instance.created,
        event_id=uuid.uuid5(uuid.NAMESPACE_DNS, str(instance.id) + TransferEvent.type + 'fiat_deposit')
    )

    get_kafka_producer().produce(event)
