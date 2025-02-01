import logging

import requests
from celery import shared_task
from decouple import config
from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from kavenegar import KavenegarAPI, APIException, HTTPException

from accounts.models import SystemConfig, TemplateType, MeliPayamakTemplate
from accounts.utils.melipayamak import MeliPayamak
from accounts.verifiers.finotech import token_cache

logger = logging.getLogger(__name__)

SMS_IR_TOKEN_KEY = 'sms-ir-token'


def send_message_by_kavenegar(phone: str, template: TemplateType, token: str, send_type: str = 'sms'):
    send_mode = SystemConfig.get_system_config().otp_send_mode
    template_str = str(template)

    if not phone or settings.DEBUG_OR_TESTING_OR_STAGING:
        return

    if send_mode == SystemConfig.OTP_KAVENEGAR_EXCLUSIVE:
        try:
            return send_kavenegar_exclusive_sms(
                phone=phone,
                content=render_to_string(f"accounts/sms/{template_str}.txt", {'token': token, 'brand': settings.BRAND})
            )
        except TemplateDoesNotExist:
            logger.info('Sending otp ignored due to no template found!')
    elif send_mode == SystemConfig.OTP_KAVENEGAR:
        client = get_kavenegar_client()

        try:
            client.verify_lookup({
                'receptor': phone,
                'template': template_str,
                'type': send_type,
                'token': token,
            })
        except (APIException, HTTPException) as e:
            logger.exception("Failed to send sms by kavenegar")
    elif send_mode == SystemConfig.MELI_PAYAMAK:
        client = get_melipayamak_client()
        try:
            body_id = MeliPayamakTemplate.get_template_code(template)
            if body_id is None:
                logger.error('MeliPayamak template not found', extra={'template': template})
                return
            client.sms().send_by_base_number(bodyId=body_id, text=token, to=phone)
        except Exception as e:
            logger.exception("Failed to send sms by melipayamak")


def get_kavenegar_client() -> KavenegarAPI:
    api_key = config('KAVENEGAR_KEY')
    return KavenegarAPI(apikey=api_key)


def get_melipayamak_client() -> MeliPayamak:
    username = config('MELIPAYAMAK_USERNAME')
    password = config('MELIPAYAMAK_PASSWORD')
    return MeliPayamak(username, password)


def send_kavenegar_exclusive_sms(phone: str, content: str):
    if not phone or settings.DEBUG_OR_TESTING_OR_STAGING or not settings.EXCLUSIVE_SMS_NUMBER:
        return True

    client = get_kavenegar_client()

    message = content + '\nلغو= 11'

    try:
        client.sms_send({
            'receptor': phone,
            'message': message,
            'sender': settings.EXCLUSIVE_SMS_NUMBER,
        })
        return True
    except (APIException, HTTPException) as e:
        logger.exception("Failed to send sms by kavenegar")

    return False


def get_sms_ir_token():
    token = token_cache.get(SMS_IR_TOKEN_KEY)

    if token:
        return token

    resp = requests.post(
        url='https://RestfulSms.com/api/Token',
        timeout=15,
        data={
            'UserApiKey': config('SMS_IR_API_KEY'),
            'SecretKey': config('SMS_IR_API_SECRET'),
        }
    )

    if resp.ok:
        resp_data = resp.json()
        token = resp_data['TokenKey']
        expire = 30 * 60

        token_cache.set(SMS_IR_TOKEN_KEY, token, expire)

        return token


@shared_task(queue='sms')
def send_message_by_sms_ir(phone: str, template: str, params: dict):
    if not phone or settings.DEBUG_OR_TESTING_OR_STAGING or not settings.EXCLUSIVE_SMS_NUMBER:
        return True

    param_array = [
        {"Parameter": key, "ParameterValue": value} for (key, value) in params.items()
    ]

    resp = requests.post(
        url='https://RestfulSms.com/api/UltraFastSend',
        json={
            "ParameterArray": param_array,
            "Mobile": phone,
            "TemplateId": template
        },
        headers={
            'x-sms-ir-secure-token': get_sms_ir_token()
        },
        timeout=20,
    )

    data = resp.json()
    print(data)

    if not resp.ok:
        return

    if not data['IsSuccessful']:
        logger.error('Failed to send sms via sms.ir', extra={
            'phone': phone,
            'template': template,
            'params': params,
            'data': data
        })

        return

    return data


@shared_task(queue='sms')
def send_message_by_sms_ir2(phone: str, template: str, params: dict):
    param_array = [
        {"name": key, "value": value} for (key, value) in params.items()
    ]

    resp = requests.post(
        url='https://api.sms.ir/v1/send/verify',
        json={
            "mobile": phone,
            "templateId": template,
            "parameters": param_array,
        },
        headers={
            'X-API-KEY': secret('SMS_IR2_API_KEY'),
            'ACCEPT': 'application/json'
        }
    )

    if not resp.ok:
        return

    data = resp.json()

    if data['status'] == 0:
        logger.error('Failed to send sms via sms.ir', extra={
            'phone': phone,
            'template': template,
            'params': params,
            'data': data
        })

        return

    return data
