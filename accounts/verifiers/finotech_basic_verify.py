import logging
from datetime import datetime, timedelta

from django.utils import timezone

from accounts.models import User
from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.utils.similarity import str_similar_rate, clean_persian_name, rotate_words
from accounts.utils.telegram import send_support_message
from accounts.verifiers.finotech import FinotechRequester, ServerError
from financial.models import BankCard, BankAccount

logger = logging.getLogger(__name__)

IBAN_NAME_SIMILARITY_THRESHOLD = 0.75


def basic_verify(user: User):
    if user.level != User.LEVEL1:
        logger.info('ignoring double verifying user_d = %d' % user.id)
        return

    if not user.national_code_verified:
        logger.info('verifying national_code for user_d = %d' % user.id)

        if not verify_national_code(user):
            return

    if not user.primary_data_verified:
        now = timezone.now().astimezone()
        hour = now.hour

        if hour >= 23 or hour < 7:
            if hour >= 23:
                target = now + timedelta(days=1)
            else:
                target = now

            next_valid = datetime(year=target.year, month=target.month, day=target.day, hour=7, minute=10, tzinfo=target.tzinfo)
            to_pass_seconds = int((next_valid - now).total_seconds())

            from accounts.tasks import basic_verify_user
            logger.info('rescheduling basic_verify to valid hours for user_id = %d' % user.id)
            basic_verify_user.s(user.id).apply_async(countdown=to_pass_seconds)
            return

        logger.info('verifying primary_data for user_d = %d' % user.id)

        if not verify_user_primary_info(user):
            return

    def get_first_verify_qs(queryset):
        return queryset.filter(verified=True).first() or queryset.filter(verified=None).first() or \
                   queryset.filter(verified=False).first()

    bank_card = get_first_verify_qs(user.bankcard_set.all())

    if not bank_card:
        user.change_status(User.REJECTED)
        logger.info('no bank card or account for user_d = %d' % user.id)
        return

    if not bank_card.verified:
        logger.info('verifying bank_card for user_d = %d' % user.id)

        if verify_bank_card(bank_card) is False:
            user.change_status(User.REJECTED)
            return

    user.verify_level2_if_not()


def verify_national_code(user: User, retry: int = 5) -> bool:
    if not user.national_code:
        return False

    requester = FinotechRequester(user)

    try:
        verified = requester.verify_phone_number_national_code(user.phone, user.national_code)
    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('Finotech timeout verify_national_code')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_national_code(user, retry - 1)

    user.national_code_verified = verified
    user.save(update_fields=['national_code_verified'])

    if not verified:
        user.change_status(User.REJECTED)
    else:
        # check duplicated national_code
        if User.objects.exclude(id=user.id).filter(national_code=user.national_code, level__gt=User.LEVEL1).exists():
            user.change_status(User.REJECTED)
            return False

        user.verify_level2_if_not()

    return verified


def verify_user_primary_info(user: User, retry: int = 5) -> bool:
    if not user.national_code_verified:
        return False

    if not user.first_name or not user.last_name or not user.birth_date:
        return False

    requester = FinotechRequester(user)

    try:
        data = requester.verify_basic_info(
            national_code=user.national_code,
            birth_date=user.birth_date,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('Finotech timeout user_primary_info')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_user_primary_info(user, retry - 1)

    user.birth_date_verified = bool(data)
    user.save(update_fields=['birth_date_verified'])

    if not data:
        user.change_status(User.REJECTED)
        return False

    similarity_sum = data['firstNameSimilarity'] + data['lastNameSimilarity']

    user.first_name_verified = data['firstNameSimilarity'] >= 70 or similarity_sum >= 150 or None
    user.last_name_verified = data['lastNameSimilarity'] >= 70 or similarity_sum >= 150 or None
    user.save(update_fields=['first_name_verified', 'last_name_verified'])

    if not user.first_name_verified or not user.last_name_verified:
        # user.change_status(User.REJECTED)

        link = url_to_edit_object(user)
        send_support_message(
            message='اطلاعات نام کاربر مورد تایید قرار نگرفت. لطفا دستی بررسی شود.',
            link=link
        )

        return False

    user.verify_level2_if_not()

    return True


def verify_bank_card(bank_card: BankCard, retry: int = 5) -> bool:
    if BankCard.live_objects.filter(card_pan=bank_card.card_pan, verified=True).exclude(id=bank_card.id).exists():
        logger.info('rejecting bank card because of duplication')
        bank_card.verified = False
        bank_card.save()
        return False

    requester = FinotechRequester(bank_card.user)

    try:
        verified = requester.verify_card_pan_phone_number(bank_card.user.phone, bank_card.card_pan)
    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('Finotech timeout bank_card')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_bank_card(bank_card, retry - 1)

    bank_card.verified = verified
    bank_card.save()

    bank_card.user.verify_level2_if_not()

    return bank_card.verified


DEPOSIT_STATUS_MAP = {
    2: BankAccount.ACTIVE,
    3: BankAccount.DEPOSITABLE_SUSPENDED,
    4: BankAccount.NON_DEPOSITABLE_SUSPENDED,
    5: BankAccount.STAGNANT,
}


def verify_bank_account(bank_account: BankAccount, retry: int = 5) -> bool:
    if BankAccount.live_objects.filter(iban=bank_account.iban, verified=True).exclude(id=bank_account.id).exists():
        logger.info('rejecting bank account because of duplication')
        bank_account.verified = False
        bank_account.save()
        return False

    requester = FinotechRequester(bank_account.user)

    try:
        data = requester.get_iban_info(bank_account.iban)

        if not data:
            link = url_to_edit_object(bank_account)
            send_support_message(
                message='تایید شماره شبای کاربر با مشکل مواجه شد. لطفا دستی بررسی شود.',
                link=link
            )
            return

    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('Finotech timeout bank_account')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_bank_account(bank_account, retry - 1)

    bank_account.bank_name = data['bankName']
    bank_account.deposit_address = data['deposit']
    bank_account.card_pan = data.get('card', '')
    bank_account.deposit_status = DEPOSIT_STATUS_MAP.get(int(data['depositStatus']), '')

    owners = bank_account.owners = data['depositOwners']

    user = bank_account.user

    verified = False
    if len(owners) >= 1:
        owner = owners[0]
        owner_full_name = owner['firstName'] + ' ' + owner['lastName']

        name1, name2 = clean_persian_name(owner_full_name), clean_persian_name(user.get_legal_name())

        verified = str_similar_rate(name1, name2) >= IBAN_NAME_SIMILARITY_THRESHOLD

        if not verified:
            name1_rotate = rotate_words(name1)

            verified = str_similar_rate(name1_rotate, name2) >= IBAN_NAME_SIMILARITY_THRESHOLD

    bank_account.verified = verified
    bank_account.save()

    bank_account.user.verify_level2_if_not()

    return verified
