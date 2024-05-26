import logging
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from accounting.models import Vault, Account
from accounting.models.periodic_fetcher import FetchError
from accounting.models.vault import VaultData, AssetPrice, VaultItem, ReservedAsset
from accounts.verifiers.utils import ServerError
from financial.models import Gateway
from financial.utils.withdraw import FiatWithdraw
from ledger.models import Asset
from ledger.requester.internal_assets_requester import get_internal_asset_deposits
from ledger.utils.price import USDT_IRT, get_symbol_parts
from ledger.utils.provider import get_provider_requester

logger = logging.getLogger(__name__)


def update_provider_vaults(now: datetime, prices: dict):
    logger.info('updating provider vaults')
    provider = get_provider_requester()

    profiles = provider.get_profiles()

    for profile in profiles:
        profile_id = profile['id']

        logger.info('updating provider profile = %d' % profile_id)

        exchange = profile['exchange']

        if exchange == 'binance':
            markets = Vault.MARKETS
        else:
            markets = [Vault.SPOT]

        for market in markets:
            vault, _ = Vault.objects.get_or_create(
                type=Vault.PROVIDER,
                market=market,
                key=profile_id,

                defaults={
                    'name': '%s-%s' % (exchange, profile['id']),
                    'updated': now,
                }
            )

            vault_data = []

            try:
                balances_data = provider.get_balances(profile_id, market)
            except TimeoutError:
                continue

            if not balances_data:
                continue

            balances = balances_data['balances']
            real_value = balances_data['real_value'] and Decimal(balances_data['real_value'])
            extra_info = balances_data.get('extra')

            if vault.extra != extra_info:
                vault.extra = extra_info
                vault.save(update_fields=['extra'])

            if balances is None:
                continue

            for coin, balance in balances.items():
                balance = Decimal(balance)

                vault_data.append(
                    VaultData(
                        coin=coin,
                        balance=balance,
                        free=balance,
                        value_usdt=balance * prices.get(coin + Asset.USDT, 0),
                        value_irt=balance * prices.get(coin + Asset.IRT, 0)
                    )
                )

            vault.update_vault_all_items(now, vault_data, real_vault_value=real_value)


def update_hot_wallet_vault(now: datetime, prices: dict):
    try:
        data = get_internal_asset_deposits()
    except FetchError:
        logger.info('updating hot wallet vaults ignored due to fetch error')
        return

    for network, asset in data.items():
        vault, _ = Vault.objects.get_or_create(
            type=Vault.HOT_WALLET,
            market=Vault.SPOT,
            key=network,
            defaults={
                'name': network,
                'updated': now,
            }
        )

        vault_data = []

        for coin, amount in asset.items():
            vault_data.append(
                VaultData(
                    coin=coin,
                    balance=amount,
                    free=amount,
                    value_usdt=amount * prices.get(coin + Asset.USDT, 0),
                    value_irt=amount * prices.get(coin + Asset.IRT, 0),
                )
            )

        vault.update_vault_all_items(now, vault_data)


def update_gateway_vaults(now: datetime, prices: dict):
    for gateway in Gateway.objects.exclude(withdraw_api_secret_encrypted=''):
        vault, _ = Vault.objects.get_or_create(
            type=Vault.GATEWAY,
            market=Vault.SPOT,
            key=gateway.id,
            defaults={
                'name': str(gateway),
                'updated': now,
            }
        )

        handler = FiatWithdraw.get_withdraw_channel(gateway)

        try:
            wallet = handler.get_wallet_data()
        except (ServerError, TimeoutError):
            continue

        balance = Decimal(wallet.balance)

        vault.update_vault_all_items(now, [
            VaultData(
                coin=Asset.IRT,
                balance=balance,
                free=Decimal(wallet.free),
                value_usdt=balance / prices[USDT_IRT],
                value_irt=balance
            )
        ])


def update_cold_wallet_vaults(now: datetime, prices: dict):
    logger.info('updating cold & manual wallet vaults')

    for vault_item in VaultItem.objects.filter(vault__type__in=(Vault.COLD_WALLET, Vault.MANUAL)):
        vault_item.value_usdt = vault_item.balance * prices.get(vault_item.coin + Asset.USDT, 0)
        vault_item.value_irt = vault_item.value_usdt * prices.get(vault_item.coin + Asset.IRT, 0)
        vault_item.save(update_fields=['value_usdt', 'value_irt'])

    for vault in Vault.objects.filter(type__in=(Vault.COLD_WALLET, Vault.MANUAL)):
        vault.update_real_value(now)


def update_bank_vaults(now: datetime, prices: dict):
    for account in Account.objects.filter(create_vault=True):
        vault, _ = Vault.objects.update_or_create(
            type=Vault.BANK,
            market=Vault.SPOT,
            key=account.id,

            defaults={
                'name': account.name,
                'updated': now,
            }
        )

        amount = account.get_balance()

        vault.update_vault_all_items(now, [
            VaultData(
                coin=Asset.IRT,
                balance=amount,
                free=amount,
                value_usdt=amount / prices[USDT_IRT],
                value_irt=amount
            )
        ])


def update_reserved_assets_value(now: datetime, prices: dict):
    for res in ReservedAsset.objects.all():
        res.value_usdt = res.amount * prices.get(res.coin + Asset.USDT, 0)
        res.value_irt = res.amount * prices.get(res.coin + Asset.IRT, 0)
        res.save(update_fields=['value_usdt', 'value_irt'])


def update_asset_prices(now: datetime, prices: dict):
    logger.info('updating asset prices')
    _prices = {}
    for symbol, price in prices.items():
        coin, base = get_symbol_parts(symbol)
        if base == Asset.USDT:
            _prices[coin] = price

    existing_assets = AssetPrice.objects.filter(coin__in=_prices)
    existing_coins = set(existing_assets.values_list('coin', flat=True))

    now = timezone.now()

    missing_assets = []
    for coin in set(_prices) - existing_coins:
        missing_assets.append(
            AssetPrice(
                updated=now,
                coin=coin,
                price=_prices.get(coin)
            )
        )

    AssetPrice.objects.bulk_create(missing_assets)

    for asset in existing_assets:
        asset.price = _prices.get(asset.coin)
        asset.updated = now

    AssetPrice.objects.bulk_update(existing_assets, ['price', 'updated'])
