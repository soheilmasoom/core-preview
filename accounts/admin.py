from decouple import config
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.admin import UserAdmin
from django.db.models import Q
from django.db.models import Sum
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from jalali_date.admin import ModelAdminJalaliMixin
from simple_history.admin import SimpleHistoryAdmin

from accounts.models import FirebaseToken, Attribution, AppStatus, VerificationCode, \
    UserFeedback, BulkNotification, EmailNotification, Consultation, SystemConfig, Forget2FA, ChangePhone
from accounts.models import UserComment, TrafficSource, Referral
from accounts.utils.admin import url_to_admin_list, url_to_edit_object
from financial.models.bank_card import BankCard, BankAccount
from financial.models.payment import Payment
from financial.models.withdraw_request import FiatWithdrawRequest
from financial.utils.withdraw_limit import get_fiat_withdraw_irt_value, get_crypto_withdraw_irt_value
from ledger.models import OTCTrade, DepositAddress, Prize, Transfer, Wallet
from ledger.utils.external_price import BUY
from ledger.utils.fields import PENDING
from ledger.utils.precision import humanize_number
from market.models import Trade, ReferralTrx, Order
from stake.models import StakeRequest
from .admin_guard import M
from .admin_guard.admin import AdvancedAdmin
from .models import User, Account, Notification, FinotechRequest, Company, LevelGrants
from .models.change_requests import BaseChangeRequest
from .models.login_activity import LoginActivity
from .models.sms_notification import SmsNotification
from .models.user_feature_perm import UserFeaturePerm
from .tasks import basic_verify_user
from .utils.mask import get_masked_phone
from .utils.validation import gregorian_to_jalali_datetime_str

MANUAL_VERIFY_CONDITION = Q(
    Q(first_name_verified=None) | Q(last_name_verified=None),
    national_code_verified=True,
    birth_date_verified=True,
    level=User.LEVEL1,
    verify_status=User.PENDING
)


class UserStatusFilter(SimpleListFilter):
    title = 'تایید سطح دو '
    parameter_name = 'status_is_pending_or_rejected'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('status_is_pending_or_rejected')
        if user is not None:
            return queryset.filter((Q(verify_status='pending') | Q(verify_status='rejected')))
        else:
            return queryset


class UserPendingStatusFilter(SimpleListFilter):
    title = 'تایید سطح  سه'
    parameter_name = 'status_is_pending'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):
        user = request.GET.get('status_is_pending')
        if user is not None:
            return queryset.filter(verify_status='pending')
        else:
            return queryset


class ManualNameVerifyFilter(SimpleListFilter):
    title = 'نیازمند تایید دستی نام'
    parameter_name = 'manual_name_verify'

    def lookups(self, request, model_admin):
        return (1, 'بله'), (0, 'خیر')

    def queryset(self, request, queryset):
        value = self.value()
        if value is not None:

            if value == '1':
                return queryset.filter(MANUAL_VERIFY_CONDITION)
            elif value == '0':
                return queryset.exclude(MANUAL_VERIFY_CONDITION)

        return queryset


class UserNationalCodeFilter(SimpleListFilter):
    title = 'کد ملی'
    parameter_name = 'national_code'

    def lookups(self, request, model_admin):
        return (1, 1),

    def queryset(self, request, queryset):
        national_code = request.GET.get('national_code')
        if national_code is not None:
            return queryset.filter(national_code=national_code).exclude(national_code='')
        else:
            return queryset


class AnotherUserFilter(SimpleListFilter):
    title = 'دیگر کاربرها'
    parameter_name = 'user_id_exclude'

    def lookups(self, request, model_admin):
        return (1, 1),

    def queryset(self, request, queryset):
        user_id = request.GET.get('user_id_exclude')
        if user_id is not None:
            return queryset.exclude(id=user_id)
        else:
            return queryset


class UserCommentInLine(admin.TabularInline):
    model = UserComment
    extra = 1
    fields = ('comment', 'created', )
    readonly_fields = ('user', 'created')


class UserFeatureInLine(admin.TabularInline):
    model = UserFeaturePerm
    extra = 1


class NotificationInLine(admin.TabularInline):
    model = Notification
    extra = 0
    fields = ('created', 'title', 'link', 'message', 'read_date')
    readonly_fields = ('created', 'title', 'link', 'message', 'read_date' )
    can_delete = False
    max_num = 10
    ordering = ('-created', )

    def has_add_permission(self, request, obj):
        return False


class UserReferredFilter(SimpleListFilter):
    title = 'لیست کاربران دعوت شده'
    parameter_name = 'owner_id'

    def lookups(self, request, model_admin):
        return [(1, 1)]

    def queryset(self, request, queryset):

        owner_id = request.GET.get('owner_id')
        if owner_id is not None:
            return queryset.filter(account__referred_by__owner__user_id=owner_id)
        else:
            return queryset


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'consulter', 'status', 'get_description',)
    readonly_fields = ('created', 'user')
    list_filter = ('status',)
    search_fields = ('user__phone', 'user__email',)

    @admin.display(description='description')
    def get_description(self, consultation: Consultation):
        n = 300
        description = consultation.description
        if len(description) > n:
            return description[:n] + '...'
        else:
            return description

    @admin.display(description='user')
    def get_username(self, consultation: Consultation):
        return mark_safe(
            f'<span dir="ltr">{consultation.user}</span>'
        )


class BaseChangeAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    actions = ('accept_requests', 'reject_requests',)
    list_filter = ('status', )

    def get_selfie_image_display(self, obj):
        return "عکس سلفی"

    @admin.action(description='رد درخواست', permissions=['view'])
    def reject_requests(self, request, queryset):
        qs = queryset.filter(status=PENDING)

        for req in qs:
            req.reject()

    @admin.action(description='تایید درخواست', permissions=['view'])
    def accept_requests(self, request, queryset):
        qs = queryset.filter(status=PENDING)

        for req in qs:
            req.accept()


@admin.register(Forget2FA)
class Forget2FAAdmin(BaseChangeAdmin):
    list_display = ('created', 'status', 'get_username',)
    readonly_fields = ('created', 'status', 'user', 'selfie_image',)

    @admin.display(description='user')
    def get_username(self, forget_2fa: Forget2FA):
        return mark_safe(
            f'<span dir="ltr">{forget_2fa.user}</span>'
        )


@admin.register(ChangePhone)
class ChangePhoneAdmin(BaseChangeAdmin):
    list_display = ('created', 'status', 'get_username', 'new_phone')
    readonly_fields = ('created', 'status', 'user', 'new_phone', 'selfie_image',)

    @admin.display(description='user')
    def get_username(self, change_phone: ChangePhone):
        return mark_safe(
            f'<span dir="ltr">{change_phone.user}</span>'
        )


@admin.register(SystemConfig)
class SystemConfigAdmin(SimpleHistoryAdmin, AdvancedAdmin):
    list_display = ('name', 'active', 'withdraw_status', 'deposit_status')
    list_editable = ('withdraw_status', 'deposit_status')

    default_edit_condition = M.superuser

    fields_edit_conditions = {
        'withdraw_status': True,
        'deposit_status': True
    }


@admin.register(User)
class CustomUserAdmin(ModelAdminJalaliMixin, SimpleHistoryAdmin, AdvancedAdmin, UserAdmin):
    default_edit_condition = M.superuser

    fields_edit_conditions = {
        'password': None,
        'first_name': True,
        'last_name': True,
        'is_staff': M.has_perm('accounts.manage_users'),
        'national_code': M.has_perm('accounts.manage_users') | ~M('national_code_verified'),
        'national_code_phone_verified': True,
        'birth_date': M.has_perm('accounts.manage_users') | ~M('birth_date_verified'),
        'selfie_image_verified': M.has_perm('accounts.manage_users') | M('selfie_image'),
        'selfie_image_discard_text': M.has_perm('accounts.manage_users') | (M('selfie_image') & M.is_none('selfie_image_verified')),
        'first_name_verified': M.has_perm('accounts.manage_users') | M.is_none('first_name_verified'),
        'last_name_verified': M.has_perm('accounts.manage_users') | M.is_none('last_name_verified'),
        'national_code_verified': M.has_perm('accounts.manage_users') | ~M('national_code_verified'),
        'birth_date_verified': M.has_perm('accounts.manage_users') | M.is_none('birth_date_verified'),
        'can_withdraw': True,
        'can_withdraw_crypto': True,
        'can_trade': True,
        'show_margin': True,
        'withdraw_limit_whitelist': M.has_perm('accounts.manage_users'),
        'withdraw_risk_level_multiplier': M.has_perm('accounts.manage_users'),
    }

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'national_code', 'email', 'phone', 'birth_date',
                                         'get_selfie_image', 'archived',
                                         'get_user_reject_reason', 'get_source_medium', 'promotion'
                                         )}),
        (_('Authentication'), {'fields': ('level', 'verify_status', 'first_name_verified',
                                          'last_name_verified', 'national_code_verified', 'national_code_phone_verified',
                                          'birth_date_verified', 'reject_reason',
                                          'selfie_image_verified', 'selfie_image_verifier',
                                          'selfie_image_discard_text',
                                          )}),
        (_('Permissions'), {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions', 'show_margin', 'show_strategy_bot', 'show_staking', 'show_community',
                'can_trade', 'can_withdraw', 'can_withdraw_crypto',
                'withdraw_limit_whitelist', 'withdraw_risk_level_multiplier', 'custom_crypto_withdraw_ceil'
            ),
        }),
        (_('Important dates'), {'fields': (
            'get_last_login_jalali', 'get_date_joined_jalali',
            'get_first_crypto_deposit_date_jalali', 'get_level_2_verify_datetime_jalali',
            'get_level_3_verify_datetime_jalali', 'get_selfie_image_uploaded',
            'margin_quiz_pass_date',
        )}),
        (_('لینک های مهم'), {
            'fields': (
                'get_wallet', 'get_transfer_link', 'get_payment_address',
                'get_withdraw_address', 'get_otctrade_address', 'get_fill_order_address', 'get_order_link',
                'get_open_order_address', 'get_deposit_address', 'get_bank_card_link',
                'get_bank_account_link', 'get_finotech_request_link', 'get_staking_link',
                'get_user_with_same_national_code', 'get_referred_user', 'get_login_activity_link',
                'get_notifications_link', 'get_prizes_link', 'get_bots_link'
            )
        }),
        (_('اطلاعات مالی کاربر'), {'fields': (
            'get_sum_of_value_buy_sell', 'get_remaining_fiat_withdraw_limit',
            'get_remaining_crypto_withdraw_limit', 'get_last_trade', 'get_total_balance_irt_admin'
        )}),
        (_("جایزه‌های دریافتی"), {'fields': ('get_user_prizes',)}),
        (_("کدهای دعوت کاربر"), {'fields': (
            'get_revenue_of_referral', 'get_referred_count', 'get_revenue_of_referred'
        )}),
        (_('اطلاعات اضافی'), {'fields': (
            'is_price_notif_on', 'get_suspended', 'suspended_until', 'suspension_reason', 'is_2fa_active'
        )})
    )

    list_display = ('get_date_joined_jalali', 'get_username', 'first_name', 'last_name', 'level', 'archived', 'get_user_reject_reason',
                    'verify_status', 'promotion', 'get_source_medium', 'get_referrer_user', 'is_price_notif_on',
                    'get_suspended',)
    list_filter = (
        'archived', ManualNameVerifyFilter, 'level', 'national_code_phone_verified', 'date_joined', 'verify_status', 'level_2_verify_datetime',
        'level_3_verify_datetime', UserStatusFilter, UserNationalCodeFilter, AnotherUserFilter, UserPendingStatusFilter,
        'is_staff', 'is_superuser', 'is_active', 'groups', UserReferredFilter,
    )
    inlines = [UserCommentInLine, UserFeatureInLine]
    ordering = ('-id', )
    actions = (
        'verify_user_name', 'reject_user_name', 'archive_users', 'unarchive_users', 'reevaluate_basic_verify',
        'verify_user', 'reject_user'
    )
    readonly_fields = (
        'get_payment_address', 'get_withdraw_address', 'get_otctrade_address', 'get_wallet',
        'get_sum_of_value_buy_sell',
        'get_selfie_image', 'get_level_2_verify_datetime_jalali', 'get_level_3_verify_datetime_jalali',
        'get_first_crypto_deposit_date_jalali',
        'get_date_joined_jalali', 'get_last_login_jalali',
        'get_remaining_fiat_withdraw_limit', 'get_remaining_crypto_withdraw_limit', 'get_deposit_address',
        'get_bank_card_link', 'get_bank_account_link', 'get_transfer_link', 'get_finotech_request_link',
        'get_user_reject_reason', 'get_user_with_same_national_code', 'get_user_prizes', 'get_source_medium',
        'get_fill_order_address', 'selfie_image_verifier', 'get_revenue_of_referral', 'get_referred_count',
        'get_revenue_of_referred', 'get_open_order_address', 'get_selfie_image_uploaded', 'get_referred_user',
        'get_login_activity_link', 'get_last_trade', 'get_total_balance_irt_admin', 'get_order_link',
        'get_notifications_link', 'get_staking_link', 'get_prizes_link', 'get_suspended',
        'suspension_reason', 'get_bots_link', 'is_2fa_active'
    )
    preserve_filters = ('archived', )

    search_fields = (*UserAdmin.search_fields, 'national_code', 'phone')

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

    @admin.display(description='2fa', boolean=True)
    def is_2fa_active(self, user: User):
        return user.is_2fa_active()

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
            user.selfie_image_verifier = request.user

        return super(CustomUserAdmin, self).save_model(request, user, form, change)

    def get_payment_address(self, user: User):
        link = url_to_admin_list(Payment)+'?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_payment_address.short_description = 'واریزهای ریالی'

    def get_fill_order_address(self, user: User):
        link = url_to_admin_list(Trade) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_fill_order_address.short_description = 'معاملات'

    def get_order_link(self, user: User):
        link = url_to_admin_list(Order) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_order_link.short_description = 'سفارشات'

    def get_bots_link(self, user: User):
        link = (config('STRATEGY_HOST_URL', 'https://strategy-api.raastin.com') +
                '/admin/bot/agent/?account_id={}'.format(user.get_account().id))
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_bots_link.short_description = 'لیست ربات‌ها'

    def get_open_order_address(self, user: User):
        link = url_to_admin_list(Order) +'?status=new&user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_open_order_address.short_description = 'سفارشات باز'

    def get_withdraw_address(self, user: User):
        link = url_to_admin_list(FiatWithdrawRequest)+'?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_withdraw_address.short_description = 'درخواست برداشت ریالی'

    def get_otctrade_address(self, user: User):
        link = url_to_admin_list(OTCTrade)+'?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_otctrade_address.short_description = 'خریدهای OTC'

    @admin.display(description='source/medium')
    def get_source_medium(self, user: User):
        if hasattr(user, 'trafficsource'):
            link = url_to_edit_object(user.trafficsource)
            text = '%s/%s' % (user.trafficsource.utm_source, user.trafficsource.utm_medium)

            return mark_safe("<a href='%s'>%s</a>" % (link, text))

    def get_referrer_user(self, user: User):
        account = getattr(user, 'account', None)
        referrer = account and account.referred_by and account.referred_by.owner.user

        if referrer:
            link = url_to_edit_object(referrer)
            return mark_safe("<a href='%s'>%s</a>" % (link, referrer.id))

    get_referrer_user.short_description = 'referrer'

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

    get_user_reject_reason.short_description = 'وضعیت احراز'

    def get_wallet(self, user: User):
        link = url_to_admin_list(Wallet) + '?account={}'.format(user.get_account().id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_wallet.short_description = 'لیست کیف‌ها'

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
        return mark_safe("<a href='%s'>دیدن</a>" % link) \

    get_transfer_link.short_description = 'تراکنش‌های رمزارزی'

    def get_finotech_request_link(self, user: User):
        link = url_to_admin_list(FinotechRequest) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_finotech_request_link.short_description = 'درخواست‌های فینوتک'

    def get_referred_user(self, user: User):

        link = url_to_admin_list(User) + '?owner_id={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_referred_user.short_description = 'کاربران دعوت شده'

    def get_login_activity_link(self, user: User):
        link = url_to_admin_list(LoginActivity) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_login_activity_link.short_description = 'تاریخچه ورود به حساب'

    def get_user_with_same_national_code(self, user: User):
        user_count = User.objects.filter(
            ~Q(id=user.id) & Q(national_code=user.national_code) & ~Q(national_code='')
        ).count()
        return mark_safe(
            "<a href='/admin/accounts/user/?national_code=%s&user_id_exclude=%s'> دیدن (%sکاربر)  </a>" % (
                user.national_code, user.id, user_count
            )
        )

    get_user_with_same_national_code.short_description = 'کاربرانی با این کد ملی'

    def get_level_2_verify_datetime_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.level_2_verify_datetime)

    get_level_2_verify_datetime_jalali.short_description = 'تاریخ تایید سطح ۲'

    def get_level_3_verify_datetime_jalali(self, user: User):
        return gregorian_to_jalali_datetime_str(user.level_3_verify_datetime)

    get_level_3_verify_datetime_jalali.short_description = 'تاریخ تایید سطح ۳'

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

    def get_remaining_crypto_withdraw_limit(self, user: User):
        return humanize_number(
            LevelGrants.get_max_daily_crypto_withdraw(user) - get_crypto_withdraw_irt_value(user)
        )

    get_remaining_crypto_withdraw_limit.short_description = 'باقی مانده سقف مجاز برداشت رمزارز   روزانه'

    def get_selfie_image(self, user: User):
        return mark_safe("<img src='%s' width='200' height='200' />" % user.selfie_image.get_absolute_image_url())

    get_selfie_image.short_description = 'عکس سلفی'

    def get_user_prizes(self, user: User):
        prizes = user.get_account().prize_set.all()
        prize_list = []
        for prize in prizes:
            prize_list.append(str(prize.achievement))
        return prize_list

    get_user_prizes.short_description = 'جایزه‌های دریافتی کاربر'

    def get_referred_count(self, user: User):
        referrals = Referral.objects.filter(owner=user.get_account())
        referred_count = 0
        for referral in referrals:
            referred_count += Account.objects.filter(referred_by=referral).count()
        return referred_count
    get_referred_count.short_description = ' تعداد دوستان دعوت شده'

    def get_revenue_of_referral(self, user: User):
        referrals = Referral.objects.filter(owner=user.get_account())
        revenues = 0
        for referral in referrals:
            revenue = ReferralTrx.objects.filter(referral=referral).aggregate(total=Sum('referrer_amount'))
            revenues += int(revenue['total'] or 0)
        return revenues

    get_revenue_of_referral.short_description = 'درآمد حاصل از کدهای دعوت ارسال شده به دوستان '

    def get_revenue_of_referred(self, user: User):
        referral = user.get_account().referred_by

        revenue = ReferralTrx.objects.filter(referral=referral).aggregate(total=Sum('trader_amount'))
        return int(revenue['total'] or 0)

    get_revenue_of_referred.short_description = 'درآمد حاصل از کد دعوت استفاده شده'

    def get_selfie_image_uploaded(self, user: User):
        latest_null = user.history.filter(selfie_image__isnull=True).order_by('history_date').last()

        if latest_null:
            history = user.history.filter(
                history_id__gt=latest_null.history_id,
                selfie_image__isnull=False
            ).order_by('history_date').first()

            if history:
                return gregorian_to_jalali_datetime_str(history.history_date)

    get_selfie_image_uploaded.short_description = 'زمان آپلود عکس سلفی'

    def get_deposit_address(self, user: User):
        link = url_to_admin_list(DepositAddress) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    get_deposit_address.short_description = 'آدرس‌های کیف پول'

    def get_total_balance_irt_admin(self, user: User):
        try:
            total_balance_irt = user.get_account().get_total_balance_irt(side=BUY)
            return humanize_number(int(total_balance_irt))
        except:
            pass

    get_total_balance_irt_admin.short_description = 'دارایی به تومان'

    @admin.display(description='اعلانات')
    def get_notifications_link(self, user: User):
        link = url_to_admin_list(Notification) + '?recipient_id={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='جوایز')
    def get_prizes_link(self, user: User):
        link = url_to_admin_list(Prize) + '?user={}'.format(user.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)

    @admin.display(description='لیست استیکینگ‌ (staking) کاربر')
    def get_staking_link(self, user: User):
        link = url_to_admin_list(StakeRequest) + '?account_id={}'.format(user.account.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'type', 'name', 'trade_volume_irt', 'custom_maker_fee', 'custom_taker_fee')
    search_fields = ('user__phone', )
    list_filter = ('type', 'primary')

    fieldsets = (
        ('اطلاعات', {'fields': (
            'name', 'user', 'type', 'primary', 'owned', 'trade_volume_irt', 'get_wallet',
            'get_total_balance_irt_admin', 'get_total_balance_usdt_admin', 'referred_by',
            'custom_maker_fee', 'custom_taker_fee'
        )}),
    )
    readonly_fields = ('user', 'get_wallet', 'get_total_balance_irt_admin', 'get_total_balance_usdt_admin',
                       'trade_volume_irt', 'referred_by',)

    def get_wallet(self, account: Account):
        link = url_to_admin_list(Wallet) + '?account={}'.format(account.id)
        return mark_safe("<a href='%s'>دیدن</a>" % link)
    get_wallet.short_description = 'لیست کیف‌ها'

    def get_total_balance_irt_admin(self, account: Account):
        total_balance_irt = account.get_total_balance_irt(side=BUY)

        return humanize_number(int(total_balance_irt))

    get_total_balance_irt_admin.short_description = 'دارایی به تومان'

    def get_total_balance_usdt_admin(self, account: Account):
        total_blance_usdt = account.get_total_balance_usdt()
        return humanize_number(int(total_blance_usdt))

    get_total_balance_usdt_admin.short_description = 'دارایی به تتر'

    @admin.display(description='user')
    def get_username(self, account: Account):
        return mark_safe(
            f'<span dir="ltr">{account.user}</span>'
        )


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'code', 'owner_share_percent')
    search_fields = ('code', 'owner__user__phone')
    readonly_fields = ('owner', )

    @admin.display(description='user')
    def get_username(self, referral: Referral):
        return mark_safe(
            f'<span dir="ltr">{referral.owner}</span>'
        )


class FinotechRequestUserFilter(SimpleListFilter):
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


@admin.register(FinotechRequest)
class FinotechRequestAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'url', 'status_code')
    list_filter = (FinotechRequestUserFilter, 'status_code')
    ordering = ('-created', )
    search_fields = ('url', 'data')
    raw_id_fields = ('user', )

    @admin.display(description='user')
    def get_username(self, req: FinotechRequest):
        return mark_safe(
            f'<span dir="ltr">{req.user}</span>'
        )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'level', 'title', 'message', 'push_status')
    list_filter = ('level', )
    search_fields = ('title', 'message', 'group_id', 'recipient__phone')
    readonly_fields = ('recipient', 'group_id')

    @admin.display(description='user')
    def get_username(self, notification: Notification):
        return mark_safe(
            f'<span dir="ltr">{notification.recipient}</span>'
        )


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = ('created', 'status', 'level', 'title', 'message')
    list_filter = ('level', )
    search_fields = ('title', 'message', 'group_id')
    readonly_fields = ('group_id', 'status')


@admin.register(SmsNotification)
class SmsNotificationAdmin(admin.ModelAdmin):
    list_display = ('created', 'recipient', 'content', 'sent')
    search_fields = ('recipient__phone', 'group_id')
    readonly_fields = ('recipient', 'group_id')
    list_filter = ('sent', )


@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = ('created', 'recipient', 'title', 'sent')
    search_fields = ('recipient__phone', 'group_id', 'title')
    readonly_fields = ('recipient', 'group_id')
    list_filter = ('sent', )


@admin.register(UserComment)
class UserCommentAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ['get_username', 'created']

    @admin.display(description='user')
    def get_username(self, user_comment: UserComment):
        return mark_safe(
            f'<span dir="ltr">{user_comment.user}</span>'
        )


@admin.register(TrafficSource)
class TrafficSourceAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ['get_username', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']
    search_fields = ['user__phone', 'gps_adid', 'ip']
    readonly_fields = ('user', )

    @admin.display(description='user')
    def get_username(self, traffic_source: TrafficSource):
        return mark_safe(
            f'<span dir="ltr">{traffic_source.user}</span>'
        )


@admin.register(LoginActivity)
class LoginActivityAdmin(admin.ModelAdmin):
    list_display = ('created', 'get_username', 'ip', 'country', 'city', 'device', 'os', 'browser', 'device_type', 'is_sign_up',
                    'native_app', 'session', 'get_jalali_created')
    search_fields = ('user__phone', 'ip', 'session__session_key')
    readonly_fields = ('user', 'session', 'ip', 'refresh_token', 'get_jalali_created')
    list_filter = ('is_sign_up', 'native_app',)

    @admin.display(description='user')
    def get_username(self, login_activity: LoginActivity):
        return mark_safe(
            f'<span dir="ltr">{login_activity.user}</span>'
        )

    @admin.display(description='created jalali')
    def get_jalali_created(self, login_activity: LoginActivity):
        return gregorian_to_jalali_datetime_str(login_activity.created)


@admin.register(FirebaseToken)
class FirebaseTokenAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ['user', 'ip', 'native_app']
    readonly_fields = ('created', 'user')
    list_filter = ('native_app', )
    search_fields = ('user__phone', 'token')


@admin.register(Attribution)
class AttributionAdmin(admin.ModelAdmin):
    list_display = ['created', 'tracker_code', 'network_name', 'campaign_name', 'adgroup_name', 'gps_adid']


@admin.register(AppStatus)
class AppStatusAdmin(admin.ModelAdmin):
    list_display = ['latest_version', 'force_update_version', 'active']

@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('created', 'phone', 'user', 'scope', 'expiration', 'code_used')
    search_fields = ('user__phone', 'phone', 'user__first_name', 'user__last_name')
    list_filter = ('scope', )
    readonly_fields = ('user', )


@admin.register(UserFeedback)
class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ['created', 'user', 'score', 'get_comment']
    search_fields = ('user__phone', 'user__first_name', 'user__last_name')
    readonly_fields = ('user', )

    @admin.display(description='comment', ordering='comment')
    def get_comment(self, feedback: UserFeedback):
        n = 300

        if len(feedback.comment) > n:
            return feedback.comment[:n] + '...'
        else:
            return feedback.comment


@admin.register(UserFeaturePerm)
class UserFeaturePermAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'limit')
    search_fields = ('user__phone', )
    list_filter = ('feature', )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('national_id', 'name', 'status',)
    readonly_fields = ('status', 'company_documents',)
    actions = ('accept_requests', 'reject_requests', 'fetch_company_info',)
    raw_id_fields = ('user',)
    list_filter = ('status',)

    @admin.action(description='رد اطلاعات', permissions=['view'])
    def reject_requests(self, request, queryset):
        for req in queryset:
            req.reject()

    @admin.action(description='تایید اطلاعات', permissions=['view'])
    def accept_requests(self, request, queryset):
        for req in queryset:
            req.accept()

    @admin.action(description='استعلام اطلاعات', permissions=['view'])
    def fetch_company_info(self, request, queryset):
        for req in queryset:
            req.verify_and_fetch_company_data()


@admin.register(LevelGrants)
class LevelGrantsAdmin(admin.ModelAdmin):
    list_display = ('level', 'max_daily_crypto_withdraw', 'max_daily_fiat_withdraw', 'max_daily_fiat_deposit')
    ordering = ('level',)
