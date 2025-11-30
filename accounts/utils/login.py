import json

from django.contrib.sessions.models import Session

from accounts.models.login_activity import LoginActivity
from accounts.models.refresh_token import RefreshToken
from accounts.utils.ip import get_client_ip, get_ip_data


def get_login_user_agent_data_from_request(request) -> dict:
    os = request.user_agent.os.family
    os_version = request.user_agent.os.version_string
    if os_version:
        os += ' ' + os_version

    device = request.user_agent.device.family

    browser = request.user_agent.browser.family
    browser_version = request.user_agent.browser.version_string

    if browser_version:
        browser += ' ' + browser_version

    if request.user_agent.is_mobile:
        device_type = LoginActivity.MOBILE
    elif request.user_agent.is_tablet:
        device_type = LoginActivity.TABLET
    elif request.user_agent.is_pc:
        device_type = LoginActivity.PC
    else:
        device_type = LoginActivity.UNKNOWN

    return {
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        'device_type': device_type,
        'device': device,
        'os': os,
        'browser': browser
    }


def get_login_user_agent_data_from_client_info(client_info: dict) -> dict:
    return {
        'user_agent': json.dumps(client_info),
        'device_type': LoginActivity.MOBILE,
        'device': client_info.get('brand', '').capitalize() + ' ' + client_info.get('model', ''),
        'os': '%s %s' % (client_info.get('system_name', ''), client_info.get('system_version', '')),
        'browser': client_info.get('brand', ''),
    }


def set_login_activity(request, user, is_sign_up: bool = False, client_info: dict = None, refresh_token: str = None):
    session = Session.objects.filter(session_key=request.session.session_key).first()

    refresh_token_model = None
    if refresh_token and not session:
        refresh_token_model, _ = RefreshToken.objects.get_or_create(token=refresh_token)

    if not (session or refresh_token):
        raise ValueError

    if client_info is not None:
        user_agent_data = get_login_user_agent_data_from_client_info(client_info)
    else:
        user_agent_data = get_login_user_agent_data_from_request(request)

    ip = get_client_ip(request)
    ip_data = get_ip_data(ip)

    login_activity, _ = LoginActivity.objects.get_or_create(
        session=session,
        refresh_token=refresh_token_model,
        defaults={
            **user_agent_data,
            'user': user,
            'is_sign_up': is_sign_up,
            'ip': ip,
            'ip_data': ip_data,
            'city': ip_data.get('city', ''),
            'country': ip_data.get('country', ''),
            'native_app': bool(refresh_token_model),
        }
    )
    return login_activity
