from django.conf import settings

from ledger.utils.wallet_pipeline import WalletPipeline

if settings.DEBUG_OR_TESTING:
    import random
    import time

    from accounts.models import Account, User, VerificationCode
    from ledger.utils.external_price import get_price_redis
    from ledger.models import Asset, AddressBook, Network, NetworkAsset
    from financial.models import BankCard, Gateway
    from market.models import PairSymbol
    from market.utils.order_utils import new_order


    def get_rand_int():
        return random.randint(0, 100000000)

    def new_account() -> Account:
        name = 'test' + str(get_rand_int())
        u = User.objects.create(username=name, phone=name)
        return u.get_account()

    def set_price(asset: Asset, ask: float, bid: float = None):
        if not bid:
            bid = ask

        assert ask >= bid

        mapping = {
            'a': ask,
            'b': bid
        }

        if asset.symbol == Asset.USDT:
            key = 'price:usdtirt'
        else:
            key = 'price:' + asset.symbol.lower() + 'usdt'

        get_price_redis(allow_stale=True).hset(name=key, mapping=mapping)

        time.sleep(1)


    def set_up_user(self):
        phone = '09355913457'
        user = User.objects.create(username=phone, password='1', phone=phone)
        return user


    def generate_otp_code(user, scope) -> VerificationCode:
        otp_code = VerificationCode.objects.create(
            phone=user.phone,
            scope=scope,
            code='1',
            user=user, )
        return otp_code.code


    def new_network() -> Network:
        symbol = 'BSC'
        name = 'BSC'
        address_regex = '[1-9]'
        network = Network.objects.create(symbol=symbol, name=name, address_regex=address_regex)

        return network


    def new_network_asset(asset: Asset, network: Network):

        asset = asset
        network = network
        withdraw_fee = '0'
        withdraw_min = '1'
        withdraw_max = '1000'
        withdraw_precision = '1'
        network_asset = NetworkAsset.objects.create(
            asset=asset,
            network=network,
            withdraw_fee=withdraw_fee,
            withdraw_min=withdraw_min,
            withdraw_max=withdraw_max,
            withdraw_precision=withdraw_precision,
            can_deposit=True,
            can_withdraw=True,
        )
        return network_asset


    def new_address_book(account, network, asset=None, address='123') -> AddressBook:
        name = 'test'
        address = address
        account = account
        network = network
        if asset:
            asset = Asset.get(asset)
        address_book = AddressBook.objects.create(name=name, address=address, account=account, network=network,
                                                  asset=asset)
        return address_book

    def new_bankcard(user) -> BankCard:
        bankcard = BankCard.objects.create(user=user, card_pan='1', verified=True, kyc=True,)
        return bankcard

    def new_zibal_gateway() -> Gateway:
        gateway = Gateway.objects.create(name='test', type=Gateway.ZIBAL, merchant_id='zibal', active=True)
        return gateway

    def create_system_order_book(symbol: PairSymbol, side: str, data: list):
        with WalletPipeline() as pipeline:
            for d in data:
                new_order(
                    pipeline=pipeline,
                    symbol=symbol,
                    account=Account.system(),
                    price=d[0],
                    amount=d[1],
                    side=side
                )
