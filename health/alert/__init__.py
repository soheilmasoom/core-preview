from health.alert.types import *

_ALERT_TYPES = [
    UnhandledCryptoWithdrawAlert, CryptoLongConfirmationAlert, UnhandledFiatWithdrawAlert, LongPendingFiatWithdrawAlert,
    CanceledOTCAlert, AssetHedgeAlert, TotalHedgeAlert, FiatHedgeAlert, RiskyMarginRatioAlert, VaultLowBaseBalanceAlert,
    VaultHighBalanceAlert, HotWalletLowBalanceAlert, VaultUpdateAlert
]

ALERTS = {t.NAME: t for t in _ALERT_TYPES}

assert len(set(ALERTS)) == len(_ALERT_TYPES)
