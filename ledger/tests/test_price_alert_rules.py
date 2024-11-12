from datetime import timedelta
from django.utils import timezone
from decimal import Decimal

from django.test import TestCase, Client

from accounts.models import Account
from accounts.utils.test import new_user
from ledger.models import Asset, OTCRequest, OTCTrade, AssetAlert
from ledger.models.asset_alert_rule import AssetAlertRule
from ledger.utils.external_price import SELL
from ledger.utils.test import new_account, set_price, create_system_order_book
from ledger.tasks.otc import handle_limit_otc_request
from market.models import PairSymbol


class PriceAlertRulesTestCase(TestCase):
    def setUp(self):
        self.btc = Asset.get('BTC')
        self.usdt = Asset.get(Asset.USDT)
        self.user = new_user()

        self.asset_alert = AssetAlert.objects.create(
            user=self.user,
            asset=self.btc,
            active=True
        )

    def _new_rule(self, trigger_price, trigger_type):
        return AssetAlertRule.objects.create(
            asset_alert=self.asset_alert,
            base_asset=self.usdt,
            trigger_price=trigger_price,
            type=trigger_type
        )

    def test_single_run(self):
        rule = self._new_rule(trigger_price=50000, trigger_type=AssetAlertRule.GTE)

        self.assertFalse(rule.update_current_price(40000))
        self.assertFalse(rule.update_current_price(49000))
        self.assertTrue(rule.update_current_price(51000))

        rule = self._new_rule(trigger_price=50000, trigger_type=AssetAlertRule.GTE)

        self.assertFalse(rule.update_current_price(60000))
        self.assertFalse(rule.update_current_price(51000))
        self.assertFalse(rule.update_current_price(49000))
        self.assertTrue(rule.update_current_price(51000))

        rule = self._new_rule(trigger_price=50000, trigger_type=AssetAlertRule.LTE)

        self.assertFalse(rule.update_current_price(40000))
        self.assertFalse(rule.update_current_price(49000))
        self.assertFalse(rule.update_current_price(51000))
        self.assertTrue(rule.update_current_price(49000))

        rule = self._new_rule(trigger_price=50000, trigger_type=AssetAlertRule.LTE)

        self.assertFalse(rule.update_current_price(60000))
        self.assertFalse(rule.update_current_price(51000))
        self.assertTrue(rule.update_current_price(49000))
