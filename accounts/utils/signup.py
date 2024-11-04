from django.db import transaction

from accounts.models import TrafficSource, User
from accounts.utils.ip import get_client_ip
import logging

logger = logging.getLogger(__name__)


def create_traffic_source(request, user, utm: dict, signup_source: str = TrafficSource.MAIN):
    def clean_data(d) -> str:
        if not d:
            d = ''

        if isinstance(d, list):
            d = d[0]

        return d[:256]

    utm_source = clean_data(utm.get('utm_source'))

    if not utm_source:
        return

    utm_medium = clean_data(utm.get('utm_medium'))
    utm_campaign = clean_data(utm.get('utm_campaign'))
    utm_content = clean_data(utm.get('utm_content'))
    utm_term = clean_data(utm.get('utm_term'))
    gps_adid = clean_data(utm.get('gps_adid'))
    profile_id = clean_data(utm.get('profile_id'))
    package_name = clean_data(utm.get('package_name'))

    if utm_source == 'pwa_app':
        if utm_term.startswith('gclid'):
            utm_medium = 'google_ads'
        elif 'google-play' in utm_term and 'organic' in utm_term:
            utm_medium = 'organic'
            utm_content = 'google_play'
        elif not profile_id:
            utm_medium = 'organic'
        else:
            from accounts.models import Attribution

            attribution = Attribution.objects.filter(profile_id=profile_id).order_by('created').last()

            if not attribution:
                utm_medium = 'organic'
            else:
                utm_medium = attribution.utm_medium
                utm_campaign = attribution.utm_campaign
                utm_content = attribution.utm_content

    TrafficSource.objects.create(
        user=user,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        utm_content=utm_content,
        utm_term=utm_term,
        gps_adid=gps_adid,
        yandex_profile_id=profile_id,
        package_name=package_name,
        ip=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:256],
        signup_source=signup_source
    )


def set_missions_to_user(user: User, promotion: str):
    from gamify.models import MissionJourney, MissionTemplate, UserMission

    journey = MissionJourney.get_by_promotion(promotion)

    if not journey:
        return

    with transaction.atomic():
        user.mission_journey = journey
        user.save(update_fields=['mission_journey'])

        missions = []
        for mission_template in MissionTemplate.objects.filter(journey=journey, active=True):
            missions.append(UserMission(user=user, mission=mission_template))

        if missions:
            UserMission.objects.bulk_create(missions)
