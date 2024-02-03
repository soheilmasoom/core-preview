from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django_otp.plugins.otp_totp.models import TOTPDevice
from import_export import resources
from import_export.admin import ExportMixin
from simple_history.admin import SimpleHistoryAdmin

from accounting.models import VaultItem, Vault
from accounts.admin_guard import M
from accounts.admin_guard.admin import AdvancedAdmin
from accounts.admin_guard.html_tags import anchor_tag
from accounts.models import User
from accounts.models.user_feature_perm import UserFeaturePerm
from accounts.utils.admin import url_to_edit_object
from accounts.utils.validation import gregorian_to_jalali_datetime
from financial.models import Gateway, PaymentRequest, Payment, BankCard, BankAccount, \
    FiatWithdrawRequest, ManualTransfer, MarketingSource, MarketingCost, PaymentIdRequest, PaymentId, \
    GeneralBankAccount, BankPaymentRequest, BankPaymentRequestReceipt
from financial.tasks import verify_bank_card_task, verify_bank_account_task
from financial.utils.encryption import encrypt
from financial.utils.payment_id_client import get_payment_id_client
from financial.utils.withdraw import FiatWithdraw
from gamify.utils import clone_model
from ledger.utils.fields import PENDING, INIT, CANCELED, DONE, PROCESS
from ledger.utils.precision import humanize_number
from ledger.utils.wallet_pipeline import WalletPipeline
from ledger.utils.withdraw_verify import RiskFactor, get_risks_html


@admin.register(Gateway)
class GatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'active', 'deposit_priority', 'active_for_staff',
                    'ipg_deposit_enable', 'pay_id_deposit_enable', 'withdraw_enable',
                    'suspended', 'get_balance', 'get_min_deposit_amount', 'get_max_deposit_amount')
    list_editable = ('active', 'active_for_staff', 'ipg_deposit_enable', 'pay_id_deposit_enable', 'withdraw_enable',
                     'deposit_priority', 'suspended')
    readonly_fields = ('get_balance', 'get_min_deposit_amount', 'get_max_deposit_amount')
    list_filter = ('active', 'type')

    @admin.display(description='balance')
    def get_balance(self, gateway: Gateway):
        v = VaultItem.objects.filter(vault__type=Vault.GATEWAY, vault__key=gateway.id).first()
        return v and v.value_irt

    @admin.display(description='min deposit')
    def get_min_deposit_amount(self, gateway: Gateway):
        return humanize_number(Decimal(gateway.min_deposit_amount))

    @admin.display(description='max deposit')
    def get_max_deposit_amount(self, gateway: Gateway):
        return humanize_number(Decimal(gateway.max_deposit_amount))

    def save_model(self, request, gateway: Gateway, form, change):
        encryption_fields = [
            'withdraw_api_key_encrypted', 'withdraw_api_secret_encrypted', 'withdraw_api_password_encrypted',
            'withdraw_refresh_token_encrypted', 'deposit_api_secret_encrypted', 'payment_id_secret_encrypted'
        ]

        old_gateway = gateway.id and Gateway.objects.get(id=gateway.id)

        for key in encryption_fields:
            value = getattr(gateway, key)

            if getattr(old_gateway, key, '') != value:
                setattr(gateway, key, encrypt(value))

        gateway.save()


class UserRialWithdrawRequestFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(bank_account__user_id=user)
        else:
            return queryset


@admin.register(FiatWithdrawRequest)
class FiatWithdrawRequestAdmin(SimpleHistoryAdmin):

    fieldsets = (
        ('اطلاعات درخواست', {'fields': ('created', 'status', 'amount', 'fee_amount', 'ref_id', 'bank_account',
         'get_withdraw_request_withdraw_time', 'get_withdraw_request_receive_time', 'gateway', 'get_risks')}),
        ('اطلاعات کاربر', {'fields': (
            'get_withdraw_request_iban', 'get_withdraw_request_user', 'get_user', 'login_activity'
        )}),
        ('نظر', {'fields': ('comment',)})
    )
    list_filter = ('status', UserRialWithdrawRequestFilter, )
    ordering = ('-created', )
    readonly_fields = (
        'created', 'bank_account', 'amount', 'get_withdraw_request_iban', 'fee_amount', 'get_risks',
        'get_withdraw_request_user', 'get_withdraw_request_receive_time', 'get_user', 'login_activity',
        'get_withdraw_request_receive_time', 'get_withdraw_request_withdraw_time'
    )
    search_fields = ('bank_account__iban', 'bank_account__user__phone')

    list_display = ('created', 'bank_account', 'get_user', 'status', 'amount', 'gateway', 'ref_id')

    actions = ('accept_withdraw_request', 'reject_withdraw_request', 'refund', 'resend_withdraw_request')

    @admin.display(description='نام و نام خانوادگی')
    def get_withdraw_request_user(self, withdraw_request: FiatWithdrawRequest):
        return withdraw_request.bank_account.user.get_full_name()

    @admin.display(description='کاربر')
    def get_user(self, withdraw_request: FiatWithdrawRequest):
        link = url_to_edit_object(withdraw_request.bank_account.user)
        return mark_safe("<span dir=\"ltr\"> <a href='%s'>%s</a></span>" % (link, withdraw_request.bank_account.user))

    @admin.display(description='شماره شبا')
    def get_withdraw_request_iban(self, withdraw_request: FiatWithdrawRequest):
        return withdraw_request.bank_account.iban

    @admin.display(description='risks')
    def get_risks(self, transfer):
        if not transfer.risks:
            return

        risks = [RiskFactor(**r) for r in transfer.risks]

        return mark_safe(get_risks_html(risks))

    @admin.display(description='زمان تقریبی واریز')
    def get_withdraw_request_receive_time(self, withdraw: FiatWithdrawRequest):
        if withdraw.receive_datetime:
            return str(gregorian_to_jalali_datetime(withdraw.receive_datetime.astimezone()))

    @admin.display(description='زمان فراخوانی برداشت')
    def get_withdraw_request_withdraw_time(self, withdraw: FiatWithdrawRequest):
        if withdraw.withdraw_datetime:
            return str(gregorian_to_jalali_datetime(withdraw.withdraw_datetime.astimezone()))

    @admin.action(description='تایید برداشت', permissions=['view'])
    def accept_withdraw_request(self, request, queryset):
        queryset.filter(status=INIT).update(status=PROCESS)

    @admin.action(description='رد برداشت', permissions=['view'])
    def reject_withdraw_request(self, request, queryset):
        valid_qs = queryset.filter(status=INIT)

        for fiat_withdraw in valid_qs:
            fiat_withdraw.change_status(CANCELED)

    @admin.action(description='Refund', permissions=['change'])
    def refund(self, request, queryset):
        valid_qs = queryset.filter(status=DONE)

        for fiat_withdraw in valid_qs:
            fiat_withdraw.refund()

    @admin.action(description='ارسال دوباره', permissions=['change'])
    def resend_withdraw_request(self, request, queryset):
        queryset.filter(status=PENDING).update(status=PROCESS)

    def save_model(self, request, obj: FiatWithdrawRequest, form, change):
        if obj.id:
            old = FiatWithdrawRequest.objects.get(id=obj.id)
            if old.status != obj.status:
                obj.change_status(obj.status)

        obj.save()


class PaymentRequestUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(bank_card__user_id=user)
        else:
            return queryset


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ('created', 'gateway', 'bank_card', 'amount', 'authority', 'payment')
    search_fields = ('bank_card__card_pan', 'amount', 'authority')
    readonly_fields = ('bank_card', 'group_id', 'payment', 'login_activity')
    list_filter = (PaymentRequestUserFilter,)


class PaymentUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(user=user)
        else:
            return queryset


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_amount', 'get_fee', 'status', 'ref_id', 'ref_status',
                    'get_card_pan', 'get_user',)
    list_filter = (PaymentUserFilter, 'status', )
    search_fields = ('ref_id', 'paymentrequest__bank_card__card_pan', 'amount', 'paymentrequest__authority',
                     'user__phone', 'user__first_name', 'user__last_name')
    readonly_fields = ('user', 'group_id')
    actions = ('refund', 'accept_deposit', 'reject_deposit')

    @admin.display(description='مقدار')
    def get_amount(self, payment: Payment):
        return humanize_number(payment.amount)

    @admin.display(description='کارمزد')
    def get_fee(self, payment: Payment):
        return humanize_number(payment.fee)

    @admin.display(description='کاربر')
    def get_user(self, payment: Payment):
        link = url_to_edit_object(payment.user)
        return mark_safe("<span dir=\"ltr\"> <a href='%s'>%s</a></span>" % (link, payment.user))

    @admin.display(description='شماره کارت')
    def get_card_pan(self, payment: Payment):
        if payment.paymentrequest:
            link = url_to_edit_object(payment.paymentrequest.bank_card)
            return mark_safe("<a href='%s'>%s</a>" % (link, payment.paymentrequest.bank_card.card_pan))

    @admin.action(description='Refund', permissions=['change'])
    def refund(self, request, queryset):
        valid_qs = queryset.filter(status=DONE)

        for payment in valid_qs:
            payment.refund()

    @admin.action(description='تایید واریز', permissions=['change'])
    def accept_deposit(self, request, queryset):
        queryset = queryset.filter(
            status=INIT,
        )

        with WalletPipeline() as pipeline:
            for payment in queryset:
                payment.accept(pipeline, ref_id=payment.ref_id, system_verify=False)

    @admin.action(description='رد واریز', permissions=['change'])
    def reject_deposit(self, request, queryset):
        for payment in queryset.filter(status=INIT):
            payment.description = 'Rejected by admin'
            payment.status = CANCELED
            payment.save(update_fields=['description', 'status'])


class BankCardUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(user_id=user)
        else:
            return queryset


@admin.register(BankCard)
class BankCardAdmin(SimpleHistoryAdmin, AdvancedAdmin):
    default_edit_condition = M.superuser

    list_display = ('created', 'card_pan', 'get_username', 'verified', 'deleted')
    list_filter = (BankCardUserFilter,)
    search_fields = ('card_pan', )
    readonly_fields = ('user', )

    actions = ['verify_bank_cards', 'verify_bank_cards_manual', 'reject_bank_cards_manual']

    fields_edit_conditions = {
        'verified': M.superuser | M('verified')
    }

    @admin.action(description='تایید خودکار شماره کارت')
    def verify_bank_cards(self, request, queryset):
        for bank_card in queryset:
            verify_bank_card_task.delay(bank_card.id)

    @admin.action(description='تایید شماره کارت')
    def verify_bank_cards_manual(self, request, queryset):
        for card in queryset:
            card.verified = True
            card.save()
            card.user.verify_level2_if_not()

    @admin.action(description='رد شماره کارت')
    def reject_bank_cards_manual(self, request, queryset):
        for card in queryset:
            card.verified = False
            card.save()

            user = card.user

            if user.level == User.LEVEL1 and user.verify_status == User.PENDING:
                user.change_status(User.REJECTED)

    @admin.display(description='user')
    def get_username(self, bank_card: BankCard):
        return mark_safe(
            f'<span dir="ltr">{bank_card.user}</span>'
        )


class BankUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(user_id=user)
        else:
            return queryset


@admin.register(BankAccount)
class BankAccountAdmin(SimpleHistoryAdmin, AdvancedAdmin):
    default_edit_condition = M.superuser

    list_display = ('created', 'iban', 'get_username', 'verified', 'deleted')
    list_filter = (BankUserFilter, )
    search_fields = ('iban', )
    readonly_fields = ('user', )

    actions = ['verify_bank_accounts_manual', 'verify_bank_accounts_auto', 'reject_bank_accounts_manual']

    fields_edit_conditions = {
        'verified': M.superuser | M('verified')
    }

    @admin.action(description='درخواست تایید خودکار شماره شبا')
    def verify_bank_accounts_auto(self, request, queryset):
        for bank_account in queryset:
            verify_bank_account_task.delay(bank_account.id)

    @admin.action(description='تایید شماره شبا')
    def verify_bank_accounts_manual(self, request, queryset):
        for bank_account in queryset:
            bank_account.verified = True
            bank_account.save()
            bank_account.user.verify_level2_if_not()

    @admin.action(description='رد شماره شبا')
    def reject_bank_accounts_manual(self, request, queryset):
        for bank_account in queryset:
            bank_account.verified = False
            bank_account.save()

            user = bank_account.user

            if user.level == User.LEVEL1 and user.verify_status == User.PENDING:
                user.change_status(User.REJECTED)

    @admin.display(description='user')
    def get_username(self, bank_account: BankAccount):
        return mark_safe(
            f'<span dir="ltr">{bank_account.user}</span>'
        )


@admin.register(MarketingSource)
class MarketingSourceAdmin(admin.ModelAdmin):
    list_display = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')
    list_filter = ('utm_source', )


@admin.register(MarketingCost)
class MarketingCostAdmin(admin.ModelAdmin):
    list_display = ('source', 'date', 'cost')
    search_fields = ('source__utm_source', )


class ManualTransferForm(forms.ModelForm):
    otp = forms.IntegerField(required=False)

    class Meta:
        model = ManualTransfer
        fields = '__all__'


@admin.register(ManualTransfer)
class ManualTransferAdmin(admin.ModelAdmin):
    form = ManualTransferForm

    list_display = ('created', 'amount', 'bank_account', 'status')
    readonly_fields = ('status', 'group_id', 'ref_id')

    def save_model(self, request, obj: ManualTransfer, form, change):
        totp = form.cleaned_data.pop('otp', None)
        device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

        if not (device and device.verify_token(totp)) and not settings.DEBUG_OR_TESTING_OR_STAGING:
            raise ValidationError('InvalidTotp')

        obj.save()

        if obj.status == ManualTransfer.PROCESS:
            handler = FiatWithdraw.get_withdraw_channel(obj.gateway)

            handler.create_withdraw(transfer=obj)

            obj.status = ManualTransfer.DONE
            obj.save(update_fields=['status'])


@admin.register(PaymentIdRequest)
class PaymentIdRequestAdmin(admin.ModelAdmin):
    list_display = ('created', 'owner', 'status', 'amount', 'get_user', 'external_ref', 'source_iban', 'deposit_time')
    search_fields = ('owner__pay_id', 'owner__user__phone', 'external_ref', 'source_iban', 'bank_ref')
    list_filter = ('status',)
    actions = ('accept', 'reject')
    readonly_fields = ('owner', 'get_user', 'payment')

    @admin.action(description='Accept', permissions=['change'])
    def accept(self, request, queryset):
        for payment_request in queryset.filter(status=PENDING):
            payment_request.accept()

    @admin.action(description='Reject', permissions=['change'])
    def reject(self, request, queryset):
        for payment_request in queryset.filter(status=PENDING):
            payment_request.reject()

    @admin.display(description='user')
    def get_user(self, payment_id_request: PaymentIdRequest):
        user = payment_id_request.owner.user
        link = url_to_edit_object(user)
        return mark_safe("<a href='%s'>%s</a>" % (link, user.get_full_name()))


@admin.register(PaymentId)
class PaymentIdAdmin(admin.ModelAdmin):
    list_display = ('created', 'updated', 'user', 'pay_id', 'verified', 'deleted')
    search_fields = ('user__phone', 'pay_id')
    list_filter = ('verified',)
    readonly_fields = ('user', )
    actions = ('check_status', )
    list_editable = ('deleted', )

    @admin.action(description='Check Status', permissions=['view'])
    def check_status(self, request, queryset):
        for payment_id in queryset.filter(verified=False):
            client = get_payment_id_client(payment_id.gateway)
            client.check_payment_id_status(payment_id)


@admin.register(GeneralBankAccount)
class GeneralBankAccountAdmin(admin.ModelAdmin):
    list_display = ('created', 'name', 'iban', 'bank', 'deposit_address')


class BankPaymentRequestAcceptFilter(SimpleListFilter):
    title = 'Accepted'
    parameter_name = 'accepted'

    def lookups(self, request, model_admin):
        return [('no', 'no'), ('yes', 'yes')]

    def queryset(self, request, queryset):
        val = self.value()
        if val is not None:
            queryset = queryset.filter(payment__isnull=val == 'no')

        return queryset


class BankPaymentRequestResource(resources.ModelResource):
    class Meta:
        model = BankPaymentRequest
        fields = ('created', 'amount', 'ref_id', 'description', 'user', )


class BankPaymentUserFilter(SimpleListFilter):
    title = 'user'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        users = User.objects.filter(userfeatureperm__feature=UserFeaturePerm.BANK_PAYMENT).order_by('id')
        return [(u.id, u.username) for u in users]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(user_id__exact=self.value())
        else:
            return queryset


@admin.register(BankPaymentRequestReceipt)
class BankPaymentRequestReceiptAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('id', 'payment_request',)
    readonly_fields = ('get_receipt_preview', )

    @admin.display(description='receipt preview')
    def get_receipt_preview(self, req: BankPaymentRequestReceipt):
        if req.receipt:
            return mark_safe("<img src='%s' width='400'/>" % req.receipt.url)


class BankPaymentRequestReceiptInline(admin.TabularInline):
    fields = ('receipt', 'get_receipt_preview')
    readonly_fields = ('get_receipt_preview', )

    @admin.display(description='receipt preview')
    def get_receipt_preview(self, req: BankPaymentRequestReceipt):
        if req.receipt:
            return anchor_tag(
                title="<img src='%s' width='100'/>" % req.receipt.url,
                url=url_to_edit_object(req)
            )

    model = BankPaymentRequestReceipt
    extra = 0


@admin.register(BankPaymentRequest)
class BankPaymentRequestAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('created', 'user', 'get_amount_preview', 'ref_id', 'destination_id', 'destination_type', 'payment')
    readonly_fields = ('group_id', 'get_amount_preview', 'payment')
    actions = ('accept_payment', 'clone_payment')
    list_filter = (BankPaymentRequestAcceptFilter, BankPaymentUserFilter)
    resource_classes = [BankPaymentRequestResource]
    list_editable = ('destination_id', 'ref_id')
    inlines = (BankPaymentRequestReceiptInline, )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(userfeatureperm__feature=UserFeaturePerm.BANK_PAYMENT)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='amount preview', ordering='amount')
    def get_amount_preview(self, req: BankPaymentRequest):
        return req.amount and humanize_number(req.amount)

    @admin.action(description='Accept')
    def accept_payment(self, request, queryset):
        for q in queryset.filter(payment__isnull=True, user__isnull=False, destination_id__isnull=False).exclude(ref_id=''):
            q.create_payment()

    @admin.action(description='Clone')
    def clone_payment(self, request, queryset):
        for q in queryset:
            q.ref_id = ''
            q.destination_id = None
            clone_model(q)
