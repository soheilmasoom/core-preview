import logging

from decouple import config

from accounts.utils.kaftar import send_message

logger = logging.getLogger(__name__)


def send_support_message(message: str, link: str):
    return
    text = message + '\n' + link

    send_message(
        profile=config('KAFTAR_SUPPORT_PROFILE', ''),
        text=text
    )


def send_system_message(message: str, link: str):
    text = message + '\n' + link

    send_message(
        profile=config('KAFTAR_SYSTEM_PROFILE', ''),
        text=text
    )
