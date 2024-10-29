import logging

from django.conf import settings
from django.template import loader

from accounts.models import User, Notification
from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.utils.similarity import name_similarity
from accounts.utils.similarity import split_names
from accounts.utils.telegram import send_support_message
from accounts.verifiers.jibit import JibitRequester
from accounts.verifiers.utils import *
from financial.models import BankCard, BankAccount

logger = logging.getLogger(__name__)


def send_shahkar_rejection_message(user):
    from accounts.tasks.send_sms import send_kavenegar_exclusive_sms

    Notification.send(
        recipient=user,
        title='مالکیت سیم‌کارت',
        message="کاربر گرامی، مالکیت سیم‌کارت شما جهت ارتقا به سطح 3 تایید نشد.",
        link="/account/verification/advanced"
    )

    context = {
        'brand': settings.BRAND,
    }
    content = loader.render_to_string(
        'accounts/notif/sms/shahkar_rejection_message.txt',
        context=context
    )
    send_kavenegar_exclusive_sms(phone=user.phone, content=content)


def shahkar_check(user: User, phone: str, national_code: str) -> Union[bool, None]:
    requester = JibitRequester(user)
    resp = requester.matching(phone_number=phone, national_code=national_code)
    if resp.success:
        if not resp.data.is_matched:
            send_shahkar_rejection_message(user)
        return resp.data.is_matched
    elif resp.data.code == 'INVALID_DATA':
        send_shahkar_rejection_message(user)
        return False
    else:
        logger.warning('shahkar not succeeded', extra={
            'user': user,
            'resp': resp.data,
            'phone': phone,
            'national_code': national_code
        })
        return


def verify_national_code_with_phone(user: User, retry: int = 2) -> Union[bool, None]:
    if user.level != User.LEVEL2:
        return False

    if not user.national_code:
        return False

    try:
        verified = shahkar_check(user, user.phone, user.national_code)

        if verified is None:
            return

    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('timeout verify_national_code')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_national_code_with_phone(user, retry - 1)

    user.national_code_phone_verified = verified
    user.save(update_fields=['national_code_phone_verified'])

    return verified


def update_bank_card_info(bank_card: BankCard, data: CardInfoData):
    bank_card.bank = data.bank_name
    bank_card.type = data.card_type
    bank_card.owner_name = data.owner_name
    bank_card.deposit_number = data.deposit_number
    bank_card.save(update_fields=['bank', 'type', 'owner_name', 'deposit_number'])


def verify_name_by_bank_card(bank_card: BankCard, retry: int = 2) -> Union[bool, None]:
    if not bank_card.kyc:
        return False

    requester = JibitRequester(bank_card.user)
    user = bank_card.user

    if user.first_name_verified and user.last_name_verified:
        logger.info('users first name and last name is already verified')
        return True

    try:
        resp = requester.get_card_info(card_pan=bank_card.card_pan)
        data = resp.data

        if resp.success:
            update_bank_card_info(bank_card, data)

            to_update_user_fields = []

            first_name, last_name = split_names(bank_card.owner_name)
            user.first_name = first_name
            user.last_name = last_name
            to_update_user_fields.extend(['first_name', 'last_name'])

            verified = first_name and last_name

            if verified:
                user.first_name_verified = user.last_name_verified = True
                to_update_user_fields.extend(['first_name_verified', 'last_name_verified'])

            user.save(update_fields=to_update_user_fields)

            if verified:
                user.verify_level2_if_not()
                return True

            else:
                link = url_to_edit_object(user)
                send_support_message(
                    message='اطلاعات نام کاربر مورد تایید قرار نگرفت. لطفا دستی بررسی شود.',
                    link=link
                )
                return

        elif data.code == 'INVALID_DATA':
            bank_card.verified = False
            bank_card.reject_reason = data.code
            bank_card.save(update_fields=['verified', 'reject_reason'])

            logger.info('card verification failed', extra={
                'bank_card': bank_card,
                'code': resp.data.code,
            })

            bank_card.user.change_status(User.REJECTED)
            return False

        else:
            logger.warning('card verification not succeeded', extra={
                'bank_card': bank_card,
                'code': resp.data.code,
            })
            return

    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('timeout bank_card')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_name_by_bank_card(bank_card, retry - 1)


def verify_bank_card(bank_card: BankCard, retry: int = 2) -> Union[bool, None]:
    if bank_card.verified:
        return

    if BankCard.live_objects.filter(card_pan=bank_card.card_pan, verified=True).exclude(id=bank_card.id).exists():
        logger.info('rejecting bank card because of duplication')
        bank_card.reject(BankCard.DUPLICATED)
        return False

    requester = JibitRequester(bank_card.user)

    try:
        resp = requester.get_card_info(card_pan=bank_card.card_pan)
        data = resp.data

        if resp.success:
            update_bank_card_info(bank_card, data)

            if bank_card.user.ban_deposit_with_credit_bank_cards and bank_card.type in BankCard.CREDIT_FAMILY_TYPES:
                bank_card.reject(BankCard.CREDIT_CARD)
                return False

            else:
                verified = name_similarity(bank_card.user.get_legal_name(), bank_card.owner_name)
                if not verified:
                    bank_card.reject(BankCard.NAME_MISMATCH)
                else:
                    bank_card.accept()

                return verified

        elif data.code == 'INVALID_DATA':
            bank_card.reject(data.code)

            return False
        else:
            logger.warning('card verification not succeeded', extra={
                'bank_card': bank_card,
                'resp': data.code,
            })
            return
    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('timeout bank_card')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_bank_card(bank_card, retry - 1)


DEPOSIT_STATUS_MAP = {
    'ACTIVE': BankAccount.ACTIVE,
    'BLOCK_WITH_DEPOSIT': BankAccount.DEPOSITABLE_SUSPENDED,
    'BLOCK_WITHOUT_DEPOSIT': BankAccount.NON_DEPOSITABLE_SUSPENDED,
    'IDLE': BankAccount.STAGNANT,
    'UNKNOWN': BankAccount.UNKNOWN,
}


def verify_bank_account(bank_account: BankAccount, retry: int = 2) -> Union[bool, None]:
    if BankAccount.live_objects.filter(iban=bank_account.iban, verified=True).exclude(id=bank_account.id).exists():
        logger.info('rejecting bank account because of duplication')
        bank_account.verified = False
        bank_account.save(update_fields=['verified'])
        return False

    requester = JibitRequester(bank_account.user)

    try:
        iban_info = requester.get_iban_info(bank_account.iban)
    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('timeout bank_account')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_bank_account(bank_account, retry - 1)

    if not iban_info.success:
        if iban_info.data.code == 'INVALID_IBAN':
            bank_account.verified = False
            bank_account.save(update_fields=['verified'])
            return False

        else:
            link = url_to_edit_object(bank_account)
            send_support_message(
                message='تایید شماره شبای کاربر با مشکل مواجه شد. لطفا دستی بررسی شود.',
                link=link
            )
            return

    bank_account.bank = iban_info.data.bank_name
    bank_account.deposit_address = iban_info.data.deposit_number
    bank_account.deposit_status = DEPOSIT_STATUS_MAP.get(iban_info.data.deposit_status, '')
    owners = bank_account.owners = iban_info.data.owners
    user = bank_account.user

    verified = False

    if bank_account.deposit_status == BankAccount.ACTIVE and len(owners) >= 1:
        owner = owners[0]
        owner_full_name = owner['firstName'] + ' ' + owner['lastName']
        verified = name_similarity(owner_full_name, user.get_legal_name())

    bank_account.verified = verified
    bank_account.save(update_fields=['verified', 'bank', 'deposit_address', 'deposit_status', 'owners'])
    return verified


def verify_bank_card_by_national_code(bank_card: BankCard, retry: int = 2) -> Union[bool, None]:
    user = bank_card.user

    if user.national_code_verified and user.birth_date_verified and bank_card.verified:
        return True

    if not user.national_code or not bank_card or not user.birth_date:
        return False

    if BankCard.live_objects.filter(card_pan=bank_card.card_pan, verified=True).exclude(id=bank_card.id).exists():
        logger.info('rejecting bank card because of duplication')
        bank_card.reject(BankCard.DUPLICATED)
        user.change_status(User.REJECTED)
        return False

    requester = JibitRequester(user)

    try:
        resp = requester.matching(
            national_code=user.national_code,
            birth_date=user.birth_date,
            card_pan=bank_card.card_pan
        )

        if resp.success:
            card_matched = resp.data.is_matched
            identity_matched = None

            if card_matched:
                identity_matched = True

        elif resp.data.code == 'INVALID_DATA':
            identity_matched = False
            card_matched = None
        else:
            logger.warning('card <-> national_code not succeeded', extra={
                'user': user,
                'resp': resp.data.code,
                'card': bank_card,
            })
            return

    except (TimeoutError, ServerError):
        if retry == 0:
            logger.error('timeout user_primary_info')
            return
        else:
            logger.info('Retrying verify_national_code...')
            return verify_bank_card_by_national_code(bank_card, retry - 1)

    user.national_code_verified = identity_matched
    user.birth_date_verified = identity_matched
    user.save(update_fields=['national_code_verified', 'birth_date_verified'])

    bank_card.verified = card_matched
    bank_card.save(update_fields=['verified'])

    if identity_matched is False or card_matched is False:
        user.change_status(User.REJECTED)
        return False
    else:
        user.verify_level2_if_not()
        return True


def basic_verify(user: User):
    if user.level != User.LEVEL1:
        logger.info('ignoring double verifying user_d = %d' % user.id)
        return

    bank_card = user.kyc_bank_card

    if not bank_card:
        logger.info('ignoring verify level2 due to no bank_account for user_d = %d' % user.id)
        return

    if not user.national_code_verified or not user.birth_date_verified or not bank_card.verified:
        logger.info('verifying national_code, birth_date, bank_card for user_d = %d' % user.id)

        if not verify_bank_card_by_national_code(bank_card):
            return

    if bank_card.verified and (not user.first_name_verified or not user.last_name_verified):
        logger.info('verifying name, bank_card for user_d = %d' % user.id)

        if not verify_name_by_bank_card(bank_card):
            return

    user.verify_level2_if_not()
