import csv
from typing import List

from decouple import config
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_permission_codename
from django.contrib.auth.admin import UserAdmin
from django.db.models import Sum
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_otp.plugins.otp_totp.models import TOTPDevice
from jalali_date.admin import ModelAdminJalaliMixin
from simple_history.admin import SimpleHistoryAdmin

from _base.utils import admin_display_for_crypto, admin_register_for_precious_metals_exchange
from accounts.admin import UserFeatureInLine, UserCommentInLine, UserStatusFilter, UserReferredFilter, \
    UserNationalCodeFilter, AnotherUserFilter, UserPendingStatusFilter, ManualNameVerifyFilter
from accounts.admin_guard.html_tags import url_to_admin_list, url_to_edit_object, admin_page_anchor
from accounts.models import Referral
from financial.models import BankCard, BankAccount, Payment
from financial.models.withdraw_request import FiatWithdrawRequest
from financial.utils.withdraw_limit import get_fiat_withdraw_irt_value, get_crypto_withdraw_irt_value
from gamify.utils import check_prize_achievements
from ledger.models import AddressKey
from ledger.models import OTCTrade, Prize, Transfer, Wallet, Trx, MarginPosition
from ledger.utils.blocklink import get_blocklink_requester
from ledger.utils.external_price import BUY
from ledger.utils.fields import DONE
from ledger.utils.precision import humanize_number
from ledger.utils.report import export_transactions
from market.models import Trade, ReferralTrx, Order
from stake.models import StakeRequest
from .admin_guard import M
from .admin_guard.admin import AdvancedAdmin
from .models import User, Account, Notification, UserAuthRequest, LevelGrants
from .models.login_activity import LoginActivity
from .tasks import basic_verify_user
from .utils.mask import get_masked_phone
from .utils.validation import gregorian_to_jalali_datetime_str


@admin_register_for_precious_metals_exchange(User)
class PreciousMetalsUserAdmin(ModelAdminJalaliMixin, SimpleHistoryAdmin, AdvancedAdmin, UserAdmin):
    default_edit_condition = M.superuser
    list_per_page = 20
    track_admin_activity = True

    fields_view_conditions = {
        'get_selfie_image': M.has_perm('accounts.can_view_user_selfie'),
        'password': M.superuser
    }

    fields_edit_conditions = {
        'password': None,
        'first_name': True,
        'last_name': True,
        'is_staff': M.has_perm('accounts.manage_users'),
        'level': M.has_perm('accounts.manage_users'),
        'verify_status': M.has_perm('accounts.manage_users'),
        'national_code': M.has_perm('accounts.manage_users') | ~M('national_code_verified'),
        'national_code_phone_verified': True,
        'birth_date': M.has_perm('accounts.manage_users') | ~M('birth_date_verified'),
        'selfie_image_verified': M.has_perm('accounts.manage_users') | M('selfie_image'),
        'selfie_image_discard_text': M.has_perm('accounts.manage_users') | (
                M('selfie_image') & M.is_none('selfie_image_verified')),
        'first_name_verified': M.has_perm('accounts.manage_users') | M.is_none('first_name_verified'),
        'last_name_verified': M.has_perm('accounts.manage_users') | M.is_none('last_name_verified'),
        'national_code_verified': M.has_perm('accounts.manage_users') | ~M('national_code_verified'),
        'birth_date_verified': M.has_perm('accounts.manage_users') | M.is_none('birth_date_verified'),
        'can_withdraw': True,
        'can_withdraw_crypto': True,
        'can_trade': True,
        'disable_trade_with_api': True,
        'show_margin': True,
        'withdraw_limit_whitelist': M.has_perm('accounts.manage_users'),
        'withdraw_risk_level_multiplier': M.has_perm('accounts.manage_users'),
    }

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'national_code', 'email', 'phone', 'birth_date',
                                         'get_selfie_image', 'archived',
                                         'get_user_reject_reason', 'get_source_medium', 'get_promotion'
                                         )}),
        (_('Authentication'), {'fields': ('level', 'verify_status', 'first_name_verified',
                                          'last_name_verified', 'national_code_verified',
                                          'national_code_phone_verified',
                                          'birth_date_verified', 'reject_reason',
                                          'selfie_image_verified', 'verifier',
                                          'selfie_image_discard_text',
                                          )}),
        (_('Permissions'), {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions', 'show_margin', 'show_strategy_bot', 'show_staking', 'show_community',
                'can_trade', 'disable_trade_with_api', 'can_withdraw', 'can_withdraw_crypto',
                'withdraw_limit_whitelist', 'withdraw_risk_level_multiplier', 'custom_crypto_withdraw_ceil',
                'ban_deposit_with_credit_bank_cards',
            ),
        }),
        (_('Important dates'), {'fields': (
            'get_last_login_jalali', 'get_date_joined_jalali', 'get_first_fiat_deposit_date_jalali',
            'get_first_crypto_deposit_date_jalali', 'get_level_2_verify_datetime_jalali',
            'get_level_3_verify_datetime_jalali', 'get_selfie_image_uploaded',
            'margin_quiz_pass_date',
        )}),
        (_('لینک های مهم'), {
            'fields': (
                'get_wallet', 'get_transfer_link', 'get_payment_address',
                'get_withdraw_address', 'get_otctrade_address', 'get_fill_order_address', 'get_order_link',
                'get_open_order_address', 'get_bank_card_link',
                'get_bank_account_link', 'get_finotech_request_link', 'get_staking_link',
                'get_referred_user', 'get_login_activity_link',
                'get_notifications_link', 'get_prizes_link', 'get_bots_link', 'get_totp', 'get_dust'
            )
        }),
        (_('فعالیت کاربر'), {'fields': (
            'get_sum_of_value_buy_sell', 'get_remaining_fiat_withdraw_limit',
            'get_remaining_crypto_withdraw_limit', 'get_last_trade', 'get_total_balance_irt_admin',
            'get_total_fiat_deposits', 'get_total_fiat_withdraws', 'get_total_crypto_deposits',
            'get_total_crypto_withdraws',
        )}),
        (_("جایزه‌های دریافتی"), {'fields': ('get_user_prizes',)}),
        (_("کدهای دعوت کاربر"), {'fields': (
            'get_revenue_of_referral', 'get_referred_count', 'get_revenue_of_referred'
        )}),
        (_('اطلاعات اضافی'), {'fields': (
            'is_price_notif_on', 'get_suspended', 'suspended_until', 'suspension_reason', 'is_2fa_active'
        )})
    )

    list_display = ('get_date_joined_jalali', 'get_username', 'first_name', 'last_name', 'level', 'archived',
                    'get_user_reject_reason', 'verify_status',)
    list_filter = (
        'archived', ManualNameVerifyFilter, 'level', 'national_code_phone_verified', 'date_joined', 'verify_status',
        'level_2_verify_datetime',
        'level_3_verify_datetime', UserStatusFilter, UserNationalCodeFilter, AnotherUserFilter, UserPendingStatusFilter,
        'is_staff', 'is_superuser', 'is_active', 'groups', UserReferredFilter,
    )
    inlines = [UserCommentInLine, UserFeatureInLine]
    ordering = ('-id',)
    actions = (
        'verify_user_name', 'reject_user_name', 'archive_users', 'unarchive_users', 'reevaluate_basic_verify',
        'verify_user', 'reject_user', 'check_achievements', 'export_transactions',
        'update_deposits', 'ban_credit_deposit', 'disable_2fa_auth', 'safe_delete_user',
    )
    readonly_fields = (
        'get_payment_address', 'get_withdraw_address', 'get_otctrade_address', 'get_wallet',
        'get_sum_of_value_buy_sell',
        'get_selfie_image', 'get_level_2_verify_datetime_jalali', 'get_level_3_verify_datetime_jalali',
        'get_first_fiat_deposit_date_jalali', 'get_first_crypto_deposit_date_jalali',
        'get_date_joined_jalali', 'get_last_login_jalali',
        'get_remaining_fiat_withdraw_limit', 'get_remaining_crypto_withdraw_limit',
        'get_bank_card_link', 'get_bank_account_link', 'get_transfer_link', 'get_finotech_request_link',
        'get_user_reject_reason', 'get_user_prizes', 'get_source_medium',
        'get_fill_order_address', 'verifier', 'get_revenue_of_referral', 'get_referred_count',
        'get_revenue_of_referred', 'get_open_order_address', 'get_selfie_image_uploaded', 'get_referred_user',
        'get_login_activity_link', 'get_last_trade', 'get_total_balance_irt_admin', 'get_order_link',
        'get_notifications_link', 'get_staking_link', 'get_prizes_link', 'get_suspended',
        'suspension_reason', 'get_bots_link', 'is_2fa_active', 'get_totp', 'get_dust', 'get_total_fiat_deposits',
        'get_total_fiat_withdraws', 'get_total_crypto_deposits', 'get_total_crypto_withdraws', 'get_promotion'
    )
    preserve_filters = ('archived',)

    search_fields = ('national_code', 'phone', 'username')

    list_permission_exclude_filters = ('id', 'phone', 'national_code')

    def has_manage_users_permission(self, request):
        opts = self.opts
        codename = get_permission_codename("manage_users", opts)
        return request.user.has_perm("%s.%s" % (opts.app_label, codename))

    @admin.action(description='حذف امن کاربر', permissions=['change'])
    def safe_delete_user(self, request, queryset: List[User]):
        for user in queryset:
            try:
                user.archive_registered_phone()
            except Exception as e:
                self.message_user(
                    request=request,
                    message=f"{str(e)} خطایی رخ داد",
                    level=messages.ERROR
                )

    @admin.action(description='تایید نام کاربر', permissions=['view'])
    def verify_user_name(self, request, queryset):
        to_verify_users = queryset.filter(level=User.LEVEL1).exclude(first_name='').exclude(last_name='')

        for user in to_verify_users:
            user.first_name_verified = True
            user.last_name_verified = True
            user.save(update_fields=['first_name_verified', 'last_name_verified'])
            basic_verify_user.delay(user.id)

    @admin.action(description='شروع احراز هویت پایه کاربر', permissions=['change'])
    def reevaluate_basic_verify(self, request, queryset):
        to_verify_users = queryset.filter(level=User.LEVEL1)

        for user in to_verify_users:
            basic_verify_user.delay(user.id)

    @admin.action(description='تایید دستی احراز هویت پایه کاربر', permissions=['change'])
    def verify_user(self, request, queryset):
        to_verify_users = queryset.filter(level=User.LEVEL1, verify_status__in=[User.INIT, User.PENDING])

        for user in to_verify_users:
            user.change_status(User.VERIFIED)

    @admin.action(description='رد دستی احراز هویت پایه کاربر', permissions=['change'])
    def reject_user(self, request, queryset):
        to_verify_users = queryset.filter(level=User.LEVEL1, verify_status__in=[User.INIT, User.PENDING])

        for user in to_verify_users:
            user.change_status(User.REJECTED)

    @admin.action(description='رد کردن نام کاربر', permissions=['view'])
    def reject_user_name(self, request, queryset):
        to_reject_users = queryset.filter(level=User.LEVEL1, verify_status=User.PENDING).distinct()

        for user in to_reject_users:
            user.change_status(User.REJECTED)

    @admin.action(description='بایگانی کاربر', permissions=['view'])
    def archive_users(self, request, queryset):
        queryset.update(archived=True)

    @admin.action(description='خارج کردن از بایگانی', permissions=['view'])
    def unarchive_users(self, request, queryset):
        queryset.update(archived=False)

    @admin.action(description='بررسی جایزه ماموریت‌ها', permissions=['view'])
    def check_achievements(self, request, queryset):
        for user in queryset:
            check_prize_achievements(user.get_account())

    @admin.action(description='خروجی تراکنش', permissions=['view'])
    def export_transactions(self, request, queryset):
        meta = self.model._meta

        response = HttpResponse(content_type='text/csv charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(['id', 'date', 'wallet', 'coin', 'amount', 'reason'])
        for user in queryset:
            for trx in export_transactions(user.get_account()):
                writer.writerow(
                    [trx['id'], trx['created'], trx['wallet_type'], trx['coin'], trx['amount'], trx['scope']])

        return response

    @admin.action(description='غیرفعال‌سازی شناسه دو عاملی', permissions=['manage_users'])
    def disable_2fa_auth(self, request, queryset):
        TOTPDevice.objects.filter(user__in=queryset.filter(is_staff=False), confirmed=True).update(confirmed=False)

    @admin.display(description='2fa', boolean=True)
    def is_2fa_active(self, user: User):
        return user.is_2fa_active()

    @admin.display(description='promotion')
    def get_promotion(self, user: User):
        if user.mission_journey:
            return mark_safe(admin_page_anchor(user.mission_journey))

    @admin.display(description='username')
    def get_username(self, user: User):
        return mark_safe(
            f'<span dir="ltr">{get_masked_phone(user.username)}</span>'
        )

    @admin.display(description='suspended', boolean=True)
    def get_suspended(self, user: User):
        return user.is_suspended

    def save_model(self, request, user: User, form, change):
        old_user = User.objects.filter(id=user.id).first()

        if not request.user.is_superuser:
            if (not old_user or not old_user.is_superuser) and user.is_superuser:
                raise Exception('Dangerous action happened!')

        if old_user and not old_user.selfie_image_verified and user.selfie_image_verified:
            user.verifier = request.user

        return super(PreciousMetalsUserAdmin, self).save_model(request, user, form, change)

    def get_payment_address(self, user: User):
        link = url_to_admin_list(Payment) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_payment_address.short_description = 'واریزهای ریالی'

    def get_fill_order_address(self, user: User):
        link = url_to_admin_list(Trade) + '?account={}'.format(user.get_account().id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_fill_order_address.short_description = 'معاملات'

    def get_order_link(self, user: User):
        link = url_to_admin_list(Order) + '?account={}'.format(user.get_account().id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_order_link.short_description = 'سفارشات'

    def get_bots_link(self, user: User):
        link = (config('STRATEGY_HOST_URL', 'https://strategy-api.raastin.com') +
                '/admin/bot/agent/?account_id={}'.format(user.get_account().id))
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_bots_link.short_description = 'لیست ربات‌ها'

    def get_open_order_address(self, user: User):
        link = url_to_admin_list(Order) + '?status__exact=new&account={}'.format(user.get_account().id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_open_order_address.short_description = 'سفارشات باز'

    def get_withdraw_address(self, user: User):
        link = url_to_admin_list(FiatWithdrawRequest) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_withdraw_address.short_description = 'درخواست برداشت ریالی'

    def get_otctrade_address(self, user: User):
        link = url_to_admin_list(OTCTrade) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_otctrade_address.short_description = 'خریدهای OTC'

    @admin.display(description='source/medium')
    def get_source_medium(self, user: User):
        source = getattr(user, 'traffic_source', None)
        if source:
            link = url_to_edit_object(source)
            text = '%s/%s' % (source.utm_source, source.utm_medium)

            return mark_safe("<a href='%s'>%s</a>" % (link, text))

    @admin.display(description='referrer')
    def get_referrer_user(self, user: User):
        account = getattr(user, 'account', None)
        referrer = account and account.referred_by and account.referred_by.owner.user

        if referrer:
            link = url_to_edit_object(referrer)
            return mark_safe("<a href='%s'>%s</a>" % (link, referrer.id))

    @admin.display(description='وضعیت احراز')
    def get_user_reject_reason(self, user: User):
        bank_card = user.kyc_bank_card

        if user.level == User.LEVEL1 and user.verify_status == User.REJECTED:
            if user.reject_reason == User.NATIONAL_CODE_DUPLICATED:
                return 'کد ملی تکراری'
            elif bank_card and bank_card.verified is False and bank_card.reject_reason == BankCard.DUPLICATED:
                return 'شماره کارت تکراری'
            elif not user.birth_date_verified:
                return 'مغایرت کد ملی،‌ شماره کارت و تاریخ تولد'
            elif not user.first_name_verified or not user.last_name_verified:
                return 'مغایرت نام'

        verify_fields = [
            'national_code_verified', 'birth_date_verified', 'first_name_verified', 'last_name_verified',
            'bank_card_verified', 'selfie_image_verified', 'national_code_phone_verified'
        ]

        for verify_field in verify_fields:
            field = verify_field[:-9]

            if field == 'bank_card':
                value = bank_card and bank_card.verified
            else:
                value = getattr(user, verify_field)

            if not value:
                status = 'رد شده' if value is False else 'نامشخص'

                if field == 'bank_card':
                    reason = 'شماره کارت'
                elif verify_field == 'national_code_phone_verified':
                    return 'شاهکار'
                else:
                    reason = getattr(User, field).field.verbose_name

                return reason + ' ' + status

        return ''

    @admin.display(description='لیست کیف‌ها')
    def get_wallet(self, user: User):
        link = url_to_admin_list(Wallet) + '?account={}'.format(user.get_account().id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='لیست totp')
    def get_totp(self, user: User):
        link = settings.HOST_URL + '/admin/otp_totp/totpdevice/?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='لیست تراکنش های خرد')
    def get_dust(self, user: User):
        link = url_to_admin_list(Trx) + f'?user={user.id}&scope__exact={Trx.DUST}'
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    def get_sum_of_value_buy_sell(self, user: User):
        if not hasattr(user, 'account'):
            return 0

        return humanize_number(user.get_account().trade_volume_irt)

    get_sum_of_value_buy_sell.short_description = 'مجموع معاملات'

    @admin.display(description='تاریخ آخرین معامله')
    def get_last_trade(self, user: User):
        account = user.get_account()

        dates = []
        last_trade = Trade.objects.filter(account=account).order_by('id').last()
        if last_trade:
            dates.append(last_trade.created)

        last_otc_trade = OTCTrade.objects.filter(otc_request__account=account).order_by('id').last()
        if last_otc_trade:
            dates.append(last_otc_trade.created)

        if dates:
            return gregorian_to_jalali_datetime_str(max(dates))

    def get_bank_card_link(self, user: User):
        link = url_to_admin_list(BankCard) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_bank_card_link.short_description = 'کارت‌های بانکی'

    def get_bank_account_link(self, user: User):
        link = url_to_admin_list(BankAccount) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_bank_account_link.short_description = 'حساب‌های بانکی'

    def get_transfer_link(self, user: User):
        link = url_to_admin_list(Transfer) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_transfer_link.short_description = 'تراکنش‌های رمزارزی'

    @admin.display(description='درخواست‌های احراز هویت')
    def get_finotech_request_link(self, user: User):
        link = url_to_admin_list(UserAuthRequest) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='کاربران دعوت شده')
    def get_referred_user(self, user: User):
        link = url_to_admin_list(User) + '?owner_id={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    def get_login_activity_link(self, user: User):
        link = url_to_admin_list(LoginActivity) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_login_activity_link.short_description = 'تاریخچه ورود به حساب'

    def get_level_2_verify_datetime_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.level_2_verify_datetime)

    get_level_2_verify_datetime_jalali.short_description = 'تاریخ تایید سطح ۲'

    def get_level_3_verify_datetime_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.level_3_verify_datetime)

    get_level_3_verify_datetime_jalali.short_description = 'تاریخ تایید سطح ۳'

    @admin.display(description='تاریخ اولین واریز ریالی')
    def get_first_fiat_deposit_date_jalali(self, user: User):
        date = gregorian_to_jalali_datetime_str(user.first_fiat_deposit_date)

        return mark_safe("<span>%s</span>" % date)

    @admin.display(description='تاریخ اولین واریز رمزارزی')
    def get_first_crypto_deposit_date_jalali(self, user: User):
        date = gregorian_to_jalali_datetime_str(user.first_crypto_deposit_date)

        return mark_safe("<span>%s</span>" % date)

    def get_date_joined_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.date_joined)

    get_date_joined_jalali.short_description = 'تاریخ پیوستن'

    def get_last_login_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.last_login)

    get_last_login_jalali.short_description = 'آخرین ورود'

    def get_remaining_fiat_withdraw_limit(self, user: User):
        return humanize_number(
            LevelGrants.get_max_daily_fiat_withdraw(user) - get_fiat_withdraw_irt_value(user)
        )

    get_remaining_fiat_withdraw_limit.short_description = 'باقی مانده سقف مجاز برداشت ریالی روزانه'

    @admin.display(description='باقی مانده سقف مجاز برداشت رمزارز روزانه')
    def get_remaining_crypto_withdraw_limit(self, user: User):
        return humanize_number(
            LevelGrants.get_max_daily_crypto_withdraw(user) - get_crypto_withdraw_irt_value(user)
        )

    @admin.display(description='عکس سلفی')
    def get_selfie_image(self, user: User):
        return mark_safe("<img src='%s' width='200' height='200' />" % user.selfie_image.get_url())

    @admin.display(description='جایزه‌های دریافتی کاربر')
    def get_user_prizes(self, user: User):
        prizes = user.get_account().prize_set.filter(fake=False).all()
        prize_list = []
        for prize in prizes:
            prize_list.append(str(prize.achievement))
        return prize_list

    @admin.display(description='تعداد دوستان دعوت شده')
    def get_referred_count(self, user: User):
        referrals = Referral.objects.filter(owner=user.get_account())
        referred_count = 0
        for referral in referrals:
            referred_count += Account.objects.filter(referred_by=referral).count()
        return referred_count

    get_referred_count.short_description = ' '

    @admin.display(description='درآمد حاصل از دعوت دوستان')
    def get_revenue_of_referral(self, user: User):
        referrals = Referral.objects.filter(owner=user.get_account())
        revenues = 0
        for referral in referrals:
            revenue = ReferralTrx.objects.filter(referral=referral).aggregate(total=Sum('referrer_amount'))
            revenues += int(revenue['total'] or 0)
        return revenues

    @admin.display(description='درآمد حاصل از کد دعوت استفاده شده')
    def get_revenue_of_referred(self, user: User):
        referral = user.get_account().referred_by

        revenue = ReferralTrx.objects.filter(referral=referral).aggregate(total=Sum('trader_amount'))
        return int(revenue['total'] or 0)

    @admin.display(description='زمان آپلود عکس سلفی')
    def get_selfie_image_uploaded(self, user: User):
        latest_null = user.history.filter(selfie_image__isnull=True).order_by('history_date').last()

        if latest_null:
            history = user.history.filter(
                history_id__gt=latest_null.history_id,
                selfie_image__isnull=False
            ).order_by('history_date').first()

            if history:
                return gregorian_to_jalali_datetime_str(history.history_date)

    @admin.display(description='دارایی به تومان')
    def get_total_balance_irt_admin(self, user: User):
        try:
            total_balance_irt = user.get_account().get_total_balance_irt(side=BUY)
            return humanize_number(int(total_balance_irt))
        except:
            pass

    @admin.display(description='مجموع واریز‌های ریالی')
    def get_total_fiat_deposits(self, user: User):
        return humanize_number(Payment.objects.filter(user=user, status=DONE).aggregate(s=Sum('amount'))['s'] or 0)

    @admin.display(description='مجموع برداشت‌های ریالی')
    def get_total_fiat_withdraws(self, user: User):
        return humanize_number(FiatWithdrawRequest.objects.filter(
            bank_account__user=user,
            status=DONE
        ).aggregate(s=Sum('amount'))['s'] or 0)

    @admin.display(description='مجموع واریز‌های رمزارزی')
    def get_total_crypto_deposits(self, user: User):
        return humanize_number(int(Transfer.objects.filter(
            wallet__account__user=user,
            status=DONE,
            deposit=True
        ).aggregate(s=Sum('irt_value'))['s'] or 0))

    @admin.display(description='مجموع برداشت‌های رمزارزی')
    def get_total_crypto_withdraws(self, user: User):
        return humanize_number(int(Transfer.objects.filter(
            wallet__account__user=user,
            status=DONE,
            deposit=False
        ).aggregate(s=Sum('irt_value'))['s'] or 0))

    @admin.display(description='اعلانات')
    def get_notifications_link(self, user: User):
        link = url_to_admin_list(Notification) + '?recipient_id={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='جوایز')
    def get_prizes_link(self, user: User):
        link = url_to_admin_list(Prize) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin_display_for_crypto(description='لیست استیکینگ‌ (staking) کاربر')
    def get_staking_link(self, user: User):
        link = url_to_admin_list(StakeRequest) + '?account={}'.format(user.account.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin_display_for_crypto(description='به روز رسانی واریزی‌های رمزارزی', permissions=['view'])
    def update_deposits(self, request, queryset):
        requester = get_blocklink_requester()

        for q in AddressKey.objects.filter(architecture='SOL', account__user__in=queryset, deleted=False):
            requester.refresh_deposits(address=q.address, arch=q.architecture)

    @admin.action(description='غیر فعال کردن واریز با کارت‌های هدیه', permissions=['change'])
    def ban_credit_deposit(self, request, queryset):
        for user in queryset:
            user.ban_deposit_by_credit_cards()
