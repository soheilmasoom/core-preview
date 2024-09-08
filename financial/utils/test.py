from django.conf import settings

from financial.models import BankCard, Gateway, FiatWithdrawRequest, BankAccount

if settings.DEBUG_OR_TESTING:
    from accounts.models import User, CustomToken

    def new_user(name='test_user', phone='09121111111', level=User.LEVEL2) -> User:
        name = name,
        phone = phone
        user = User.objects.create(username=name, phone=phone, level=level)
        return user

    def new_bank_card(user: User) -> BankCard:
        bank_card = BankCard.live_objects.create(user=user, card_pan='6104337574599260', verified=True)
        return bank_card

    def new_custom_token(user: User) -> str:
        token, _ = CustomToken.objects.get_or_create(user=user)
        return token.key

    def new_bank_account(user: User) -> BankAccount:
        bank_account = BankAccount.objects.create(user=user, iban='IR231245664676589495374398')
        return bank_account

    def new_gate_way() ->Gateway:
        name ='test_gateway'
        type = Gateway.PAYIR
        gateway = Gateway.objects.create(name=name, type=type, merchant_id='test', active=True)
        return gateway

    def new_fiat_withdraw_request(amount, wallet, bank_account, datetime, fee_amount=0) -> FiatWithdrawRequest:
        return FiatWithdrawRequest.objects.create(
            amount=amount,
            fee_amount=fee_amount,
            bank_account=bank_account,
            withdraw_datetime=datetime,
        )
