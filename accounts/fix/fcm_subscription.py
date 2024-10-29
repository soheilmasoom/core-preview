from ledger.models import AssetAlert


def subscribe_all():
    for asset_alert in AssetAlert.objects.order_by('id'):
        user = asset_alert.user
        topic = f"price_alerts_{asset_alert.asset.symbol.lower()}"
        fcm_topic_subscription, created = FCMTopicSubscription.objects.get_or_create(
            user=user,
            topic=topic,
            action='subscribe',
        )
