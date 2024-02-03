from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum, Q, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from django_otp.plugins.otp_totp.models import TOTPDevice
from simple_history.admin import SimpleHistoryAdmin

from accounting.models import AssetPrice
from accounting.models import ReservedAsset
from accounts.admin_guard import M
from accounts.admin_guard.admin import AdvancedAdmin
from accounts.admin_guard.html_tags import anchor_tag
from accounts.admin_guard.utils.html import get_table_html
from accounts.models import Account
from accounts.models.user_feature_perm import UserFeaturePerm
from accounts.utils.admin import url_to_edit_object
from accounts.utils.validation import gregorian_to_jalali_datetime_str
from financial.models import Payment
from gamify.utils import clone_model
from ledger import models
from ledger.models import Prize, CoinCategory, FastBuyToken, Network, ManualTransaction, Wallet, \
    ManualTrade, Trx, NetworkAsset, FeedbackCategory, WithdrawFeedback, DepositRecoveryRequest, TokenRebrand, \
    MarginHistoryModel, MarginPosition, MarginLeverage
from ledger.models.asset_alert import AssetAlert, AlertTrigger, BulkAssetAlert
from ledger.models.wallet import ReserveWallet
from ledger.utils.external_price import BUY
from ledger.utils.fields import DONE, PROCESS, PENDING, CANCELED, INIT
from ledger.utils.precision import get_presentation_amount, humanize_number, get_margin_coin_presentation_balance, \
    floor_precision
from ledger.utils.provider import get_provider_requester
from ledger.utils.withdraw_verify import RiskFactor, get_risks_html
from market.utils.fix import create_symbols_for_asset
from .models import Asset, BalanceLock
from .tasks import update_network_fees
from .utils.price import get_last_price
from .utils.wallet_pipeline import WalletPipeline


class CoinCategoryInline(admin.TabularInline):
    model = CoinCategory.coins.through
    extra = 1


@admin.register(models.Asset)
class AssetAdmin(AdvancedAdmin):
    default_edit_condition = M.superuser
    fields_edit_conditions = {
        'order': True,
        'trend': True,
    }
    list_display = (
        'symbol', 'enable', 'get_hedge_value', 'get_hedge_value_abs', 'get_hedge_amount', 'get_calc_hedge_amount',
        'get_total_asset', 'get_users_balance', 'get_reserved_amount',
        'order', 'trend', 'trade_enable', 'hedge',
        'publish_date', 'spread_category', 'otc_status', 'price_page', 'get_distribution_factor', 'margin_interest_fee'
    )
    list_filter = ('enable', 'trend', 'spread_category', 'coincategory', )
    list_editable = ('enable', 'order', 'trend', 'trade_enable', 'hedge', 'price_page')
    search_fields = ('symbol',)
    ordering = ('-enable', '-pin_to_top', '-trend', 'order')
    actions = ('setup_asset',)
    readonly_fields = ('distribution_factor',)
    inlines = (CoinCategoryInline, )

    def save_model(self, request, obj, form, change):
        if Asset.objects.filter(order=obj.order).exclude(id=obj.id).exists():
            Asset.objects.filter(order__gte=obj.order).exclude(id=obj.id).update(order=F('order') + 1)

        return super(AssetAdmin, self).save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super(AssetAdmin, self).get_queryset(request).annotate(
            hedge_value=F('assetsnapshot__hedge_value'),
            hedge_value_abs=F('assetsnapshot__hedge_value_abs'),
            hedge_amount=F('assetsnapshot__hedge_amount'),
            calc_hedge_amount=F('assetsnapshot__calc_hedge_amount'),
            users_amount=F('assetsnapshot__users_amount'),
            total_amount=F('assetsnapshot__total_amount'),
        )

    @admin.display(description='users')
    def get_users_balance(self, asset: Asset):
        users_amount = asset.users_amount

        if users_amount is None:
            return

        return humanize_number(users_amount)

    @admin.display(description='total assets')
    def get_total_asset(self, asset: Asset):
        total_amount = asset.total_amount

        if total_amount is None:
            return

        return humanize_number(total_amount)

    @admin.display(description='hedge amount')
    def get_hedge_amount(self, asset: Asset):
        hedge_amount = asset.hedge_amount

        if hedge_amount is None:
            return

        return humanize_number(hedge_amount)

    @admin.display(description='calc hedge amount')
    def get_calc_hedge_amount(self, asset: Asset):
        calc_hedge_amount = asset.calc_hedge_amount

        if calc_hedge_amount is None:
            return

        return humanize_number(calc_hedge_amount)

    @admin.display(description='dist factor', ordering='distribution_factor')
    def get_distribution_factor(self, asset: Asset):
        return round(asset.distribution_factor, 3)

    @admin.display(description='reserved amount')
    def get_reserved_amount(self, asset: Asset):
        return ReservedAsset.objects.filter(coin=asset.symbol).aggregate(s=Sum('amount'))['s']

    @admin.display(description='hedge value', ordering='hedge_value')
    def get_hedge_value(self, asset: Asset):
        hedge_value = asset.hedge_value

        if hedge_value is None:
            return

        hedge_value = round(hedge_value, 2)

        return humanize_number(hedge_value)

    @admin.display(description='hedge value abs', ordering='hedge_value_abs')
    def get_hedge_value_abs(self, asset: Asset):
        hedge_value_abs = asset.hedge_value_abs

        if hedge_value_abs is None:
            return

        hedge_value_abs = round(hedge_value_abs, 2)

        return humanize_number(hedge_value_abs)

    @admin.action(description='Setup Asset', permissions=['view'])
    def setup_asset(self, request, queryset):
        from ledger.models import NetworkAsset
        now = timezone.now()

        for asset in queryset:
            networks_info = get_provider_requester().get_network_info(asset.symbol)

            for info in networks_info:
                network, _ = Network.objects.get_or_create(
                    symbol=info.network,
                    defaults={
                        'can_deposit': False,
                        'can_withdraw': False,
                        'address_regex': info.address_regex
                    }
                )

                ns, _ = NetworkAsset.objects.get_or_create(
                    asset=asset,
                    network=network,

                    defaults={
                        'withdraw_fee': info.withdraw_fee,
                        'withdraw_min': info.withdraw_min,
                        'withdraw_max': info.withdraw_max,
                        'withdraw_precision': 0,
                    }
                )

                ns.update_with_provider(info, now)

            create_symbols_for_asset(asset)


@admin.register(FeedbackCategory)
class FeedbackCategoryAdmin(admin.ModelAdmin):
    list_display = ('category', 'order')
    list_editable = ('order', )


@admin.register(WithdrawFeedback)
class WithdrawFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'description')
    readonly_fields = ('user',)
    search_fields = ('user__phone', )
    list_filter = ('category', )


@admin.register(models.Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = (
        'symbol', 'can_withdraw', 'can_deposit', 'min_confirm', 'unlock_confirm', 'need_memo', 'address_regex',
        'slow_withdraw'
    )
    list_editable = ('can_withdraw', 'can_deposit', 'slow_withdraw')
    search_fields = ('symbol',)
    list_filter = ('can_withdraw', 'can_deposit')
    ordering = ('-can_withdraw', '-can_deposit')


@admin.register(NetworkAsset)
class NetworkAssetAdmin(admin.ModelAdmin):
    list_display = ('network', 'asset', 'get_withdraw_fee', 'get_withdraw_min', 'get_withdraw_max', 'get_deposit_min',
                    'can_deposit', 'can_withdraw', 'allow_provider_withdraw', 'hedger_withdraw_enable',
                    'update_fee_with_provider', 'last_provider_update', 'expected_hw_balance')
    search_fields = ('asset__symbol',)
    list_editable = ('can_deposit', 'can_withdraw', 'allow_provider_withdraw', 'hedger_withdraw_enable',
                     'update_fee_with_provider', 'expected_hw_balance')
    list_filter = ('can_deposit', 'can_withdraw', 'network', 'allow_provider_withdraw', 'hedger_withdraw_enable',
                   'update_fee_with_provider', )
    actions = ('update_fees', )

    @admin.display(description='withdraw_fee', ordering='withdraw_fee')
    def get_withdraw_fee(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_fee)

    @admin.display(description='withdraw_min', ordering='withdraw_min')
    def get_withdraw_min(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_min)

    @admin.display(description='withdraw_max', ordering='withdraw_max')
    def get_withdraw_max(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.withdraw_max)

    @admin.display(description='deposit_min', ordering='deposit_min')
    def get_deposit_min(self, network_asset: NetworkAsset):
        return get_presentation_amount(network_asset.deposit_min)

    @admin.action(description='Update Fees', permissions=['change'])
    def update_fees(self, request, queryset):
        update_network_fees(queryset)


class DepositAddressUserFilter(admin.SimpleListFilter):
    title = 'کاربران'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(address_key__account__user=user)
        else:
            return queryset


@admin.register(models.DepositAddress)
class DepositAddressAdmin(admin.ModelAdmin):
    list_display = ('address_key', 'network', 'address', 'get_memo', 'get_deleted')
    readonly_fields = ('address_key', 'network', 'address', 'get_memo', 'get_deleted')
    list_filter = ('network', DepositAddressUserFilter)
    search_fields = ('address',)

    @admin.display(description='memo')
    def get_memo(self, deposit_address: models.DepositAddress):
        return deposit_address.address_key.memo

    @admin.display(description='deleted', ordering='address_key__deleted', boolean=True)
    def get_deleted(self, deposit_address: models.DepositAddress):
        return deposit_address.address_key.deleted


class OTCRequestUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(account__user_id=user)
        else:
            return queryset


@admin.register(models.OTCRequest)
class OTCRequestAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'symbol', 'side', 'price', 'amount', 'fee_amount', 'fee_revenue')
    readonly_fields = ('account', 'login_activity')
    search_fields = ('token', 'symbol__name')
    list_filter = (OTCRequestUserFilter,)

    @admin.display(description='user')
    def get_username(self, otc_request: models.OTCRequest):
        return mark_safe(
            f'<span dir="ltr">{otc_request.account.user}</span>'
        )


class OTCUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(otc_request__account__user_id=user)
        else:
            return queryset


@admin.register(models.OTCTrade)
class OTCTradeAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'otc_request', 'status', 'get_value', 'get_value_irt',
                    'execution_type', 'gap_revenue', 'hedged')
    list_filter = (OTCUserFilter, 'status', 'execution_type', 'hedged')
    search_fields = ('group_id', 'order_id', 'otc_request__symbol__asset__symbol', 'otc_request__account__user__phone')
    readonly_fields = ('otc_request', 'get_username')
    actions = ('accept_trade', 'accept_trade_without_hedge', 'cancel_trade', 'revert')

    def get_queryset(self, request):
        return super(OTCTradeAdmin, self).get_queryset(request).prefetch_related('otc_request__account__user')

    @admin.display(description='value')
    def get_value(self, otc_trade: models.OTCTrade):
        return humanize_number(round(otc_trade.otc_request.usdt_value, 2))

    @admin.display(description='value_irt')
    def get_value_irt(self, otc_trade: models.OTCTrade):
        return humanize_number(round(otc_trade.otc_request.irt_value, 0))

    @admin.display(description='user')
    def get_username(self, otc_trade: models.OTCTrade):
        return anchor_tag(
            title=f'<span dir="ltr">{otc_trade.otc_request.account.user}</span>',
            url=url_to_edit_object(otc_trade.otc_request.account.user)
        )

    @admin.action(description='Accept Trade')
    def accept_trade(self, request, queryset):
        for otc in queryset.filter(status=PENDING):
            otc.hedge_with_provider()

    @admin.action(description='Accept without Hedge')
    def accept_trade_without_hedge(self, request, queryset):
        for otc in queryset.filter(status=PENDING):
            otc.hedge_with_provider(hedge=False)

    @admin.action(description='Cancel Trade')
    def cancel_trade(self, request, queryset):
        for otc in queryset.filter(status=PENDING):
            otc.cancel()

    @admin.action(description='Revert')
    def revert(self, request, queryset):
        for otc in queryset.filter(status=DONE):
            otc.revert()


@admin.register(models.Trx)
class TrxAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_masked_sender', 'get_masked_receiver', 'amount', 'scope', 'group_id')
    search_fields = (
        'sender__asset__symbol', 'sender__account__user__phone', 'receiver__account__user__phone', 'group_id')
    readonly_fields = ('sender', 'receiver',)
    list_filter = ('scope',)

    @admin.display(description='sender')
    def get_masked_sender(self, trx: Trx):
        return mark_safe(
            f'<span dir="ltr">{trx.sender}</span>'
        )

    @admin.display(description='reciever')
    def get_masked_receiver(self, trx: Trx):
        return mark_safe(
            f'<span dir="ltr">{trx.receiver}</span>'
        )


class WalletUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'account'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        account = request.GET.get('account')
        if account is not None:
            return queryset.filter(account=account)
        else:
            return queryset


class BalanceLockInline(admin.TabularInline):
    model = BalanceLock

    verbose_name = "Balance Lock Reasons"
    verbose_name_plural = "Balance Lock Reasons"
    extra = 0

    fields = ('reason', 'original_amount', 'amount', 'key')
    readonly_fields = ('reason', 'original_amount', 'amount', 'key')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(Q(amount__gt=0))


class WalletBalanceFilter(SimpleListFilter):
    title = 'Balance'
    parameter_name = 'balance'

    def lookups(self, request, model_admin):
        return [('non_zero', 'non_zero')]

    def queryset(self, request, queryset):
        if self.value() == 'non_zero':
            queryset = queryset.filter(balance__gt=0)
        return queryset


@admin.register(models.Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'asset', 'market', 'get_free', 'locked', 'get_value_usdt', 'get_value_irt',
                    'credit', 'variant')
    inlines = [BalanceLockInline]
    list_filter = [
        ('asset', RelatedDropdownFilter),
        WalletUserFilter,
        WalletBalanceFilter
    ]
    readonly_fields = ('account', 'asset', 'market', 'balance', 'locked', 'variant')
    search_fields = ('account__user__phone', 'asset__symbol')
    actions = ('sync_wallet_lock', )

    def get_queryset(self, request):
        qs = super(WalletAdmin, self).get_queryset(request)
        asset_prices = AssetPrice.objects.filter(coin=OuterRef('asset__symbol'))

        return qs.annotate(
            value=Coalesce(
                Subquery(asset_prices.values_list('price', flat=True)), Value(Decimal(0))
            ) * F('balance'),
            free=F('balance') - F('locked')
        )

    @admin.display(description='free', ordering='free')
    def get_free(self, wallet: models.Wallet):
        return humanize_number(wallet.get_free())

    @admin.display(description='irt value', ordering='value')
    def get_value_irt(self, wallet: models.Wallet):
        price = get_last_price(wallet.asset.symbol + Asset.IRT) or 0
        return humanize_number(wallet.balance * price)

    @admin.display(description='usdt value', ordering='value')
    def get_value_usdt(self, wallet: models.Wallet):
        price = get_last_price(wallet.asset.symbol + Asset.USDT) or 0
        return humanize_number(wallet.balance * price)

    @admin.display(description='user')
    def get_username(self, wallet: Wallet):
        return mark_safe(
            f'<span dir="ltr">{wallet.account}</span>'
        )

    @admin.action(description='Sync Lock', permissions=['change'])
    def sync_wallet_lock(self, request, queryset):
        for wallet in queryset:
            wallet.locked = BalanceLock.objects.filter(wallet=wallet, amount__gt=0).aggregate(sum=Sum('amount'))['sum'] or 0
            wallet.save(update_fields=['locked'])


class TransferUserFilter(SimpleListFilter):
    title = 'کاربر'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(wallet__account__user_id=user)
        else:
            return queryset


@admin.register(models.Transfer)
class TransferAdmin(SimpleHistoryAdmin, AdvancedAdmin):
    default_edit_condition = M.superuser

    fields_edit_conditions = {
        'comment': True,
        'status': True,
        'trx_hash': True,
    }

    list_display = (
        'created', 'network', 'get_asset', 'amount', 'fee_amount', 'deposit', 'status', 'source', 'get_user',
        'usdt_value', 'get_remaining_time_to_pass_48h', 'get_jalali_created', 'get_jalali_finished', 'out_address',
    )
    search_fields = ('trx_hash', 'out_address', 'wallet__asset__symbol', 'wallet__account__user__phone')
    list_filter = ('deposit', 'status', 'source', TransferUserFilter,)
    readonly_fields = (
        'deposit_address', 'network', 'wallet', 'created', 'accepted_datetime', 'finished_datetime', 'get_risks',
        'out_address', 'memo', 'amount', 'irt_value', 'usdt_value', 'deposit', 'group_id', 'login_activity',
        'address_book', 'accepted_by'
    )
    exclude = ('risks',)

    actions = ('accept_withdraw', 'reject_withdraw', 'accept_deposit', 'reject_deposit')

    def save_model(self, request, obj: models.Transfer, form, change):
        if obj.id and obj.status == DONE:
            old = models.Transfer.objects.get(id=obj.id)

            if old.status != DONE:
                old.accept(obj.trx_hash)

        obj.save()

    def get_queryset(self, request):
        return super(TransferAdmin, self).get_queryset(request).select_related('wallet__account__user')

    @admin.display(description='Asset')
    def get_asset(self, transfer: models.Transfer):
        return transfer.wallet.asset

    @admin.display(description='created jalali')
    def get_jalali_created(self, transfer: models.Transfer):
        return gregorian_to_jalali_datetime_str(transfer.created)

    @admin.display(description='finished jalali')
    def get_jalali_finished(self, transfer: models.Transfer):
        return transfer.finished_datetime and gregorian_to_jalali_datetime_str(transfer.finished_datetime)

    @admin.display(description='User')
    def get_user(self, transfer: models.Transfer):
        user = transfer.wallet.account.user

        if user:
            link = url_to_edit_object(user)
            return mark_safe("<span dir=\"ltr\"> <a href='%s'>%s</a></span>" % (link, user))

    @admin.display(description='Remaining 48h')
    def get_remaining_time_to_pass_48h(self, transfer: models.Transfer):
        if transfer.deposit:
            return

        user = transfer.wallet.account.user

        last_payment = Payment.objects.filter(
            user=user,
            created__gt=timezone.now() - timedelta(days=3),
            created__lt=transfer.created,
            status=DONE,
        ).order_by('created').last()

        if last_payment:
            passed = timezone.now() - last_payment.created
            rem = timedelta(days=2) - passed
            return '%s روز %s ساعت %s دقیقه' % (rem.days, rem.seconds // 3600, rem.seconds % 3600 // 60)

    @admin.display(description='risks')
    def get_risks(self, transfer):
        if not transfer.risks:
            return

        risks = [RiskFactor(**r) for r in transfer.risks]

        return mark_safe(get_risks_html(risks))

    @admin.action(description='تایید برداشت', permissions=['view'])
    def accept_withdraw(self, request, queryset):
        queryset.filter(
            status=INIT,
            deposit=False,
        ).update(
            status=PROCESS,
            accepted_datetime=timezone.now(),
            accepted_by=request.user
        )

    @admin.action(description='رد برداشت', permissions=['view'])
    def reject_withdraw(self, request, queryset):
        for transfer in queryset.filter(deposit=False, status=INIT):
            transfer.reject()

    @admin.action(description='تایید واریز', permissions=['change'])
    def accept_deposit(self, request, queryset):
        queryset = queryset.filter(
            status=INIT,
            deposit=True,
        )

        with transaction.atomic():
            queryset.update(accepted_datetime=timezone.now())

            for transfer in queryset:
                transfer.accept()

    @admin.action(description='رد واریز', permissions=['change'])
    def reject_deposit(self, request, queryset):
        for transfer in queryset.filter(deposit=False, status=INIT):
            transfer.reject()


class CryptoAccountTypeFilter(SimpleListFilter):
    title = 'type'
    parameter_name = 'type'

    def lookups(self, request, model_admin):
        return (Account.SYSTEM, 'system'), (Account.OUT, 'out'), ('ord', 'ordinary')

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'ord':
                value = None

            return queryset.filter(deposit_address__address_key__account__type=value)
        else:
            return queryset


@admin.register(models.MarginTransfer)
class MarginTransferAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'amount', 'type',)
    search_fields = ('group_id',)


@admin.register(models.AddressBook)
class AddressBookAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_username', 'network', 'address', 'asset',)
    search_fields = ('address', 'name')
    raw_id_fields = ('account', )
    actions = ('clone', )

    @admin.display(description='user')
    def get_username(self, address_book: models.AddressBook):
        return mark_safe(
            f'<span dir="ltr">{address_book.account}</span>'
        )

    @admin.action(description='Clone')
    def clone(self, request, queryset):
        for q in queryset:
            clone_model(q)


class PrizeUserFilter(admin.SimpleListFilter):
    title = 'کاربران'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('user')
        if user is not None:
            return queryset.filter(account__user_id=user)
        else:
            return queryset


@admin.register(models.Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ('created', 'achievement', 'get_username', 'get_asset_amount', 'redeemed', 'value')
    readonly_fields = ('account', 'asset',)
    list_filter = ('achievement', 'redeemed', PrizeUserFilter)

    def get_asset_amount(self, prize: Prize):
        return '%s %s' % (get_presentation_amount(prize.amount), prize.asset)

    get_asset_amount.short_description = 'مقدار'

    @admin.display(description='user')
    def get_username(self, prize: models.Prize):
        return mark_safe(
            f'<span dir="ltr">{prize.account.user}</span>'
        )


@admin.register(models.CoinCategory)
class CoinCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'get_coin_count', 'order')
    list_editable = ('order',)

    def get_coin_count(self, coin_category: CoinCategory):
        return coin_category.coins.filter(enable=True).count()

    get_coin_count.short_description = 'تعداد رمزارز'


@admin.register(models.AddressKey)
class AddressKeyAdmin(admin.ModelAdmin):
    list_display = ('address', 'deleted', 'account', 'architecture')
    readonly_fields = ('address', 'account')
    search_fields = ('address', 'public_address', 'account__user__phone')
    list_filter = ('architecture', 'deleted', 'architecture')


@admin.register(models.AssetSpreadCategory)
class AssetSpreadCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(models.MarketSpread)
class MarketSpreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'step', 'side', 'spread')
    list_editable = ('side', 'step', 'spread')
    ordering = ('step', 'side')
    list_filter = ('side', 'step')


@admin.register(models.PNLHistory)
class PNLHistoryAdmin(admin.ModelAdmin):
    list_display = ('date', 'get_username', 'market', 'base_asset', 'snapshot_balance', 'profit')
    readonly_fields = ('date', 'account', 'market', 'base_asset', 'snapshot_balance', 'profit')

    @admin.display(description='user')
    def get_username(self, pnl_history: models.PNLHistory):
        return mark_safe(
            f'<span dir="ltr">{pnl_history.account.user}</span>'
        )


@admin.register(models.CategorySpread)
class CategorySpreadAdmin(admin.ModelAdmin):
    list_display = ('category', 'step', 'side', 'spread')
    list_editable = ('side', 'step', 'spread')
    ordering = ('category', 'step', 'side')
    list_filter = ('category', 'side', 'step')


class SystemSnapshotVerifiedFilter(admin.SimpleListFilter):
    title = 'verified'
    parameter_name = 'verified'

    def lookups(self, request, model_admin):
        return [(1, 'بله'), (0, 'نه')]

    def queryset(self, request, queryset):
        verified = request.GET.get('verified')
        if verified is None:
            return queryset
        elif verified == '1':
            last_obj = models.SystemSnapshot.objects.last()
            return queryset.filter(Q(verified=True) | Q(verified=False, id=last_obj and last_obj.id))
        else:
            return queryset.filter(verified=False)


@admin.register(models.SystemSnapshot)
class SystemSnapshotAdmin(admin.ModelAdmin):
    list_display = ('created', 'total', 'users', 'exchange', 'get_non_reserved', 'hedge', 'reserved', 'prize', 'verified')
    ordering = ('-created',)
    actions = ('reject_histories', 'verify_histories')
    readonly_fields = ('created',)
    list_filter = (SystemSnapshotVerifiedFilter,)

    @admin.action(description='رد', permissions=['change'])
    def reject_histories(self, request, queryset):
        queryset.update(verified=False)

    @admin.action(description='تایید', permissions=['change'])
    def verify_histories(self, request, queryset):
        queryset.update(verified=True)

    @admin.display(description='non reserved')
    def get_non_reserved(self, snapshot: models.SystemSnapshot):
        return snapshot.exchange - snapshot.reserved


@admin.register(models.AssetSnapshot)
class AssetSnapshotAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ('updated', 'asset', 'total_amount', 'users_amount', 'hedge_amount', 'hedge_value', 'get_hedge_diff')
    ordering = ('asset__order',)
    list_filter = ('asset',)

    def get_hedge_diff(self, asset_snapshot: models.AssetSnapshot):
        return asset_snapshot.calc_hedge_amount - asset_snapshot.hedge_amount

    get_hedge_diff.short_description = 'hedge diff'


@admin.register(models.FastBuyToken)
class FastBuyTokenAdmin(admin.ModelAdmin):
    list_display = ('created', 'asset', 'get_amount', 'status',)
    readonly_fields = ('get_amount', 'payment_request', 'otc_request')
    list_filter = ('status',)

    def get_amount(self, fast_buy_token: FastBuyToken):
        return humanize_number(fast_buy_token.amount)

    get_amount.short_description = 'مقدار'


class ManualTransactionForm(forms.ModelForm):
    user = forms.IntegerField(required=False)
    asset = forms.ModelChoiceField(required=False, queryset=Asset.objects.filter(enable=True))
    market = forms.ChoiceField(choices=Wallet.MARKET_CHOICES, initial=Wallet.SPOT)
    wallet = forms.IntegerField(required=False, disabled=True)
    otp = forms.IntegerField(required=False)

    def clean(self):
        wallet_id = self.cleaned_data['wallet']
        if not wallet_id:
            account = Account.objects.filter(user_id=self.cleaned_data['user']).first()
            if not account:
                self.add_error('user', _("Please specify valid user id"))
                return
            asset = self.cleaned_data['asset']
            if not asset:
                self.add_error('asset', _("Please specify asset"))
                return
            self.cleaned_data['wallet'] = asset.get_wallet(account, market=self.cleaned_data['market'])
        else:
            self.cleaned_data['wallet'] = Wallet.objects.get(id=wallet_id)

        return super(ManualTransactionForm, self).clean()

    class Meta:
        model = ManualTransaction
        fields = '__all__'


@admin.register(ManualTransaction)
class ManualTransactionAdmin(admin.ModelAdmin):
    form = ManualTransactionForm
    list_display = ('created', 'wallet', 'type', 'status', 'get_amount_preview')
    list_filter = ('type', 'status')
    ordering = ('-created',)
    readonly_fields = ('group_id', 'status')
    actions = ('accept_transaction', 'reject_transaction', 'clone_transaction',)

    @admin.action(description='Accept')
    def accept_transaction(self, request, queryset):
        for trx in queryset:
            trx.change_status(DONE)

    @admin.action(description='Reject')
    def reject_transaction(self, request, queryset):
        for trx in queryset:
            trx.change_status(CANCELED)

    @admin.action(description='Clone')
    def clone_transaction(self, request, queryset):
        for trx in queryset:
            trx.id = None
            trx.status = PROCESS
            trx.group_id = uuid4()
            trx.save()

    @admin.display(description='amount', ordering='amount')
    def get_amount_preview(self, mt: ManualTransaction):
        return humanize_number(mt.amount)

    def save_model(self, request, obj, form, change):
        totp = form.cleaned_data.pop('otp', None)
        device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

        if not (device and device.verify_token(totp)) and not settings.DEBUG_OR_TESTING_OR_STAGING:
            raise ValidationError('InvalidTotp')

        super().save_model(request, obj, form, change)


@admin.register(AssetAlert)
class AssetAlertAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'asset',)
    search_fields = ['user__username', 'asset__symbol']
    raw_id_fields = ['user']

    @admin.display(description='username')
    def get_username(self, alert: AssetAlert):
        return mark_safe(
            f'<span dir="ltr">{alert.user}</span>'
        )


@admin.register(BalanceLock)
class BalanceLockAdmin(admin.ModelAdmin):
    list_display = ('created', 'key', 'wallet', 'original_amount', 'amount', 'reason')
    readonly_fields = ('wallet', 'key', 'original_amount', 'amount', 'reason')
    list_filter = ('reason',)
    search_fields = ('wallet__account__user__phone', 'key')


@admin.register(BulkAssetAlert)
class BulkAssetAlertAdmin(admin.ModelAdmin):
    list_display = ('created', 'user', 'subscription_type', 'coin_category',)
    readonly_fields = ('created',)
    search_fields = ('user__name', 'subscription_type', 'coin_category',)
    list_filter = ('subscription_type', 'coin_category',)
    raw_id_fields = ('user',)


@admin.register(ReserveWallet)
class ReserveWalletAdmin(admin.ModelAdmin):
    list_display = ('created', 'sender', 'receiver', 'amount', 'group_id', 'refund_completed', 'request_id')
    readonly_fields = ('created', 'sender', 'receiver', 'group_id')
    search_fields = ('group_id', 'request_id')


@admin.register(ManualTrade)
class ManualTradeAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'side', 'amount', 'price', 'filled_price', 'status')
    list_filter = ('side', 'status')
    ordering = ('-created',)
    readonly_fields = ('group_id', 'status')
    actions = ('accept_trade',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "account":
            kwargs["queryset"] = Account.objects.filter(user__userfeatureperm__feature=UserFeaturePerm.BANK_PAYMENT)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.action(description='Accept Trade')
    def accept_trade(self, request, queryset):
        system_base = Asset.get(Asset.IRT).get_wallet(Account.system())
        system_coin = Asset.get(Asset.USDT).get_wallet(Account.system())

        for trade in queryset.filter(status=PENDING):
            with WalletPipeline() as pipeline:
                account_base = Asset.get(Asset.IRT).get_wallet(trade.account)
                account_coin = Asset.get(Asset.USDT).get_wallet(trade.account)

                if trade.side == BUY:
                    base_sender, base_receiver = account_base, system_base
                    coin_sender, coin_receiver = system_coin, account_coin
                else:
                    base_sender, base_receiver = system_base, account_base
                    coin_sender, coin_receiver = account_coin, system_coin

                pipeline.new_trx(
                    sender=base_sender,
                    receiver=base_receiver,
                    amount=trade.price * trade.amount,
                    scope=Trx.TRADE,
                    group_id=trade.group_id
                )
                pipeline.new_trx(
                    sender=coin_sender,
                    receiver=coin_receiver,
                    amount=trade.amount,
                    scope=Trx.TRADE,
                    group_id=trade.group_id
                )
                trade.status = DONE
                trade.save(update_fields=['status'])


@admin.register(AlertTrigger)
class AlertTriggerAdmin(admin.ModelAdmin):
    list_display = (
        'created', 'asset', 'price', 'change_percent', 'chanel', 'is_chanel_changed', 'cycle', 'interval',
        'is_triggered',)
    list_filter = ('asset', 'is_chanel_changed', 'is_triggered',)
    readonly_fields = ('created', 'asset', 'price', 'change_percent', 'chanel', 'cycle',)
    search_fields = ('cycle',)


@admin.register(DepositRecoveryRequest)
class DepositRecoveryRequestAdmin(admin.ModelAdmin):
    list_display = ('coin', 'amount', 'get_description',)
    list_filter = ('status', 'coin',)
    readonly_fields = ('created', 'status', 'user', 'receiver_address', 'coin', 'network', 'amount', 'image',)
    actions = ('accept_requests', 'reject_requests', 'final_accept_requests',)
    raw_id_fields = ('user',)

    @admin.display(description='description')
    def get_description(self, deposit_request: DepositRecoveryRequest):
        n = 300
        description = deposit_request.description
        if len(description) > n:
            return description[:n] + '...'
        else:
            return description

    @admin.action(description='تایید نهایی', permissions=['change'])
    def final_accept_requests(self, request, queryset):
        qs = queryset.filter(status=PENDING)
        for req in qs:
            req.create_transfer()

    @admin.action(description='تایید اولیه', permissions=['view'])
    def accept_requests(self, request, queryset):
        qs = queryset.filter(status=PROCESS)
        for req in qs:
            req.accept()

    @admin.action(description='رد اطلاعات', permissions=['view'])
    def reject_requests(self, request, queryset):
        qs = queryset.filter(status=PROCESS)
        for req in qs:
            req.reject()


@admin.register(TokenRebrand)
class TokenRebrandAdmin(admin.ModelAdmin):
    list_display = ('created', 'old_asset', 'new_asset', 'new_asset_multiplier', 'status')
    readonly_fields = ('status', 'group_id', 'get_rebrand_info')
    actions = ('accept_for_testers', 'accept', 'reject')

    @admin.action(description='Accept', permissions=['change'])
    def accept(self, request, queryset):
        for rebrand in queryset.filter(status=PENDING):
            rebrand.accept()

    @admin.action(description='Test', permissions=['change'])
    def accept_for_testers(self, request, queryset):
        for rebrand in queryset.filter(status=PENDING):
            with WalletPipeline() as pipeline:
                rebrand.transfer_funds(pipeline, only_testers=True)

    @admin.action(description='Reject', permissions=['change'])
    def reject(self, request, queryset):
        for rebrand in queryset.filter(status=PENDING):
            rebrand.reject()

    @admin.display(description='Rebrand Info')
    def get_rebrand_info(self, token_rebrand: TokenRebrand):
        rows = [{'name': k, 'value': v} for (k, v) in token_rebrand.get_rebrand_info().__dict__.items()]
        return mark_safe(get_table_html(['name', 'value'], rows))


class PositionStatusFilter(SimpleListFilter):
    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        lookups = [(MarginPosition.OPEN, MarginPosition.OPEN), (MarginPosition.CLOSED, MarginPosition.CLOSED),
                   (MarginPosition.TERMINATING, MarginPosition.TERMINATING), ('live', 'live')]
        return lookups

    def queryset(self, request, queryset):
        status_filter = request.GET.get('status')
        if status_filter is not None:
            if status_filter in MarginPosition.STATUS_LIST:
                queryset = queryset.filter(status=status_filter)
            elif status_filter == 'live':
                queryset = queryset.filter(status=MarginPosition.OPEN, liquidation_price__isnull=False)
        return queryset


@admin.register(MarginPosition)
class MarginPositionAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'symbol', 'side', 'status', 'leverage', 'get_equity', 'amount',
                    'get_liquidation_price', 'get_average_price', 'get_orders', 'get_trades')
    readonly_fields = ('account', 'asset_wallet', 'base_wallet', 'symbol', 'amount', 'average_price', 'side',
                       'liquidation_price', 'status', 'leverage', 'equity', 'group_id')
    list_filter = (PositionStatusFilter, 'side', 'symbol')
    search_fields = ('symbol__name', 'status',)

    @admin.display(description='Orders')
    def get_orders(self, obj):
        url = reverse('admin:market_order_changelist') + f'?position={obj.id}'
        return format_html('<a href="{}">Orders</a>', url)

    @admin.display(description='Trades')
    def get_trades(self, obj):
        url = reverse('admin:market_trade_changelist') + f'?position={obj.id}'
        return format_html('<a href="{}">Trades</a>', url)

    @admin.display(description='Equity')
    def get_equity(self, obj):
        return get_margin_coin_presentation_balance(obj.symbol.base_asset.symbol, obj.equity)

    @admin.display(description='Liquidation Price')
    def get_liquidation_price(self, obj):
        price = obj.liquidation_price
        if price is not None:
            price = floor_precision(obj.liquidation_price, obj.symbol.tick_size)
        return price

    @admin.display(description='Average Price')
    def get_average_price(self, obj):
        price = obj.average_price
        if price is not None:
            price = floor_precision(obj.average_price, obj.symbol.tick_size)
        return price


@admin.register(MarginHistoryModel)
class MarginHistoryModelAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'position', 'asset', 'amount', 'type')
    readonly_fields = ('created', 'position', 'asset', 'amount', 'type', 'group_id', 'account')
    search_fields = ('group_id', 'asset__symbol', 'position__symbol__name', 'type')
    list_filter = ('type', 'asset')


@admin.register(MarginLeverage)
class MarginLeverageAdmin(admin.ModelAdmin):
    list_display = ('created', 'account', 'leverage')

