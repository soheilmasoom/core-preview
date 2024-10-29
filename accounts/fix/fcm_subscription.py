from accounts.utils.fcm_topic import fcm_topic_manager
from ledger.models import AssetAlert


def subscribe_all():
    for asset_alert in AssetAlert.objects.order_by('id'):
        topic = AssetAlert.get_default_rule_push_topic(asset_alert.asset)
        tokens = list(asset_alert.user.fcm_tokens.filter(active=True).values_list('token', flat=True))
        fcm_topic_manager.subscribe(topic, tokens)
