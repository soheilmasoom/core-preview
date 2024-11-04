from accounts.models import FirebaseToken, User
from accounts.utils.fcm_topic import fcm_topic_manager
from ledger.models import AssetAlert


def subscribe_alert(asset_alert: AssetAlert):
    topic = AssetAlert.get_default_rule_push_topic(asset_alert.asset)
    tokens = list(asset_alert.user.fcm_tokens.filter(active=True).values_list('token', flat=True))
    fcm_topic_manager.subscribe(topic, tokens)


def unsubscribe_alert(asset_alert: AssetAlert):
    topic = AssetAlert.get_default_rule_push_topic(asset_alert.asset)
    tokens = list(asset_alert.user.fcm_tokens.filter(active=True).values_list('token', flat=True))
    fcm_topic_manager.unsubscribe(topic, tokens)


def subscribe_user_to_alerts(user: User):
    for alert in AssetAlert.live_objects.filter(user=user):
        subscribe_alert(alert)


def unsubscribe_user_to_alerts(user: User):
    for alert in AssetAlert.live_objects.filter(user=user):
        unsubscribe_alert(alert)


def subscribe_token_to_alert(token: FirebaseToken):
    if not token.user:
        return

    for asset_alert in token.user.asset_alerts.all():  # type: AssetAlert
        topic = AssetAlert.get_default_rule_push_topic(asset_alert.asset)
        fcm_topic_manager.subscribe(topic, [token.token])


def resubscribe_all_alerts():
    for asset_alert in AssetAlert.live_objects.order_by('id'):
        subscribe_alert(asset_alert)
