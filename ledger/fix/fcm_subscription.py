from accounts.models.fcm_topic_subscription import FCMTopicSubscription
from ledger.models import AssetAlert


for asset_alert in AssetAlert.objects.all():
    user = asset_alert.user
    topic = f"price_alerts_{asset_alert.asset.symbol.lower()}"
    fcm_topic_subscription, created = FCMTopicSubscription.objects.get_or_create(
        user=user,
        topic=topic,
        action='subscribe',
    )
