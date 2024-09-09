import datetime
import logging

import requests
from decouple import config
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError

from accounts.utils.similarity import split_names
from accounts.models import User, UserAuthRequest
from accounts.verifiers.utils import *

logger = logging.getLogger(__name__)


class ZibalRequester:
    BASE_URL = 'https://api.zibal.ir'

    RESULT_MAP = {
        1: 'SUCCESSFUL',
        2: 'INVALID_API_KEY',
        3: 'WRONG_API_KEY',
        4: 'PERMISSION_DENIED',
        5: 'INVALID_CALL_BACK_URL',
        6: 'INVALID_DATA',
        7: 'INVALID_IP',
        8: 'INACTIVE_API_KEY',
        9: 'LOWER_THAN_MINIMUM_AMOUNT',
        21: 'INVALID_IBAN',
        29: 'INSUFFICIENT_FUNDING',
        44: 'IBAN_NOT_FOUND',
        45: 'SERVICE_UNAVAILABLE'
    }

    def __init__(self, user: User):
        self._user = user

    def collect_api(self, path: str, method: str = 'GET', data=None, weight: int = 0, search_key: str = '') -> Response:
        if search_key:
            request = UserAuthRequest.objects.filter(
                created__gt=timezone.now() - datetime.timedelta(days=30),
                search_key=search_key,
                service=UserAuthRequest.ZIBAL,
            ).order_by('-created').first()

            if request:
                if request.status_code >= 500:
                    raise ServerError('Zibal verifier request error')

                return Response(data=request.response, success=request.status_code in (200, 201))

        if data is None:
            data = {}
        url = self.BASE_URL + path

        req_object = UserAuthRequest(
            url=url,
            method=method,
            data=data,
            user=self._user,
            service=UserAuthRequest.ZIBAL,
            weight=weight,
        )

        request_kwargs = {
            'url': url,
            'timeout': 30,
            'headers': {'Authorization': 'Bearer ' + config('ZIBAL_KYC_API_TOKEN')}
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)

        except (requests.exceptions.ConnectionError, ReadTimeoutError, requests.exceptions.Timeout):
            req_object.response = 'timeout'
            req_object.status_code = 100
            req_object.save()

            logger.error('zibal connection error', extra={
                'path': path,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        resp_data = resp.json()
        req_object.response = resp_data
        req_object.status_code = resp.status_code

        if search_key and resp.status_code not in (403, 401) and resp.status_code < 500:
            req_object.search_key = search_key

        req_object.save()

        if resp.status_code >= 500:
            logger.error('failed to call zibal', extra={
                'path': path,
                'method': method,
                'data': data,
                'resp': resp_data,
                'status': resp.status_code
            })

            raise ServerError('Zibal verifier request error')

        resp = Response(data=resp_data, status_code=resp.ok)
        return resp

    def matching(self, phone_number: str = None, national_code: str = None) -> Response:
        params = {
            "mobile": phone_number,
            "nationalCode": national_code
        }

        resp = self.collect_api(
            data=params,
            path='/v1/facility/shahkarInquiry',
            method='POST',
            weight=UserAuthRequest.JIBIT_ADVANCED_MATCHING if national_code else UserAuthRequest.JIBIT_SIMPLE_MATCHING,
            search_key=f'shahkar-{phone_number}-{national_code}'
        )
        data = resp.data.get('data', {})
        resp.data = MatchingData(
            is_matched=data.get('matched', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def get_iban_info(self, iban: str) -> Response:
        params = {
            "IBAN": iban,
        }
        resp = self.collect_api(
            data=params,
            path='/v1/facility/ibanInquiry',
            method='POST',
            weight=UserAuthRequest.JIBIT_IBAN_INFO_WEIGHT,
            search_key=f'iban-{iban}'
        )
        data = resp.data.get('data', {})
        resp.data = IBANInfoData(
            bank_name=data.get('bankName', ''),
            owners=[{
                'firstName': split_names(data.get('name', ''))[0],
                'lastName': split_names(data.get('name', ''))[1]
            }],
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def get_card_info(self, card_pan: str) -> Response:
        params = {
            "cardNumber": card_pan,
        }
        resp = self.collect_api(
            path='/v1/facility/cardInquiry',
            method='POST',
            data=params,
            weight=UserAuthRequest.JIBIT_CARD_INFO_WEIGHT,
            search_key=f'card-{card_pan}'
        )
        data = resp.data.get('data', {})
        resp.data = CardInfoData(
            owner_name=data.get('name', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def national_identity_matching(self, national_code: str, birth_date: str) -> Response:
        params = {
            "nationalCode": national_code,
            "birthDate": birth_date  # todo check format: "1374/11/23"
        }
        resp = self.collect_api(
            path="/v1/facility/nationalIdentityInquiry",
            method="POST",
            data=params,
            search_key=f'nationalCode-{national_code}-{birth_date}'
        )
        data = resp.data.get('data', {})
        resp.data = NationalIdentityData(
            is_matched=data.get('matched', False),
            first_name=data.get('firstName', ''),
            last_name=data.get('lastName', ''),
            father_name=data.get('fatherName', ''),
            is_alive=data.get('alive', False),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def card_to_iban(self, card_pan: str) -> Response:
        params = {
            "cardNumber": card_pan
        }
        resp = self.collect_api(
            path="/v1/facility/cardToIban",
            method='POST',
            data=params,
            search_key=f'cardToIban-{card_pan}'
        )
        data = resp.data.get('data', {})
        resp.data = CardToIBANData(
            owner_name=data.get('name', ''),
            IBAN=data.get('IBAN', ''),
            bank_name=data.get('bankName', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def postal_code_to_address(self, postal_code: str) -> Response:
        params = {
            "postalCode": postal_code
        }
        resp = self.collect_api(
            path="/v1/facility/postalCodeInquiry",
            method="POST",
            data=params,
            search_key=f'postalCode-{postal_code}'
        )
        data = resp.data.get('data', {})
        resp.data = PostalToAddressData(
            Address(
                province=data.get('province', ''),
                town=data.get('town', ''),
                district=data.get('district', ''),
                street=data.get('street', ''),
                street2=data.get('street2', ''),
                number=data.get('number', 0),
                floor=data.get('floor', ''),
                side_floor=data.get('sideFloor', ''),
                building_name=data.get('buildingName', ''),
                description=data.get('description', '')
            ),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def iban_owner_matching(self, iban: str, name: str) -> Response:
        params = {
            "IBAN": iban,
            "name": name
        }
        resp = self.collect_api(
            path="/v1/facility/checkIBANWithName",
            method="POST",
            data=params,
            search_key=f'ibanName-{iban}-{name}'
        )
        data = resp.data.get('data', {})
        resp.data = MatchingData(
            is_matched=data.get('matched', False),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def card_owner_matching(self, card_pan: str, name: str) -> Response:
        params = {
            "cardNumber": card_pan,
            "name": name
        }
        resp = self.collect_api(
            path="/v1/facility/checkCardWithName",
            method="POST",
            data=params,
            search_key=f'cardName-{card_pan}-{name}'
        )
        data = resp.data.get('data', {})
        resp.data = MatchingData(
            is_matched=data.get('matched', False),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    # todo: check account name on project
    def card_to_account(self, card_number: str) -> Response:
        params = {
            "cardNumber": card_number
        }
        resp = self.collect_api(
            path="/v1/facility/cardToAccount",
            method="POST",
            data=params,
            search_key=f'cardAccount-{card_number}'
        )
        data = resp.data.get('data', {})
        resp.data = CardToAccountData(
            owner_name=data.get('name', ''),
            bank_name=data.get('bankName', ''),
            bank_account=data.get('bankAccount', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def national_code_card_matching(self, national_code: str, card_pan: str,  birth_date: datetime = None) -> Response:
        if birth_date:
            from accounts.utils.validation import gregorian_to_jalali_date_str
            birth_date = gregorian_to_jalali_date_str(birth_date).replace('/', '')

        params = {
            "nationalCode": national_code,
            "birthDate": birth_date,
            "cardNumber": card_pan
        }
        resp = self.collect_api(
            path="/v1/facility/checkCardWithNationalCode",
            method="POST",
            data=params,
            search_key=f'cardNationalCode-{national_code}-{birth_date}-{card_pan}'
        )
        data = resp.data.get('data', {})
        resp.data = MatchingData(
            is_matched=data.get('matched', False),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def national_code_iban_matching(self, national_code: str, birth_date: str, iban: str) -> Response:
        params = {
            "nationalCode": national_code,
            "birthDate": birth_date,
            "IBAN": iban
        }
        resp = self.collect_api(
            path="/v1/facility/checkIbanWithNationalCode",
            method="POST",
            data=params,
            search_key=f'ibanNationalCode-{national_code}-{birth_date}-{iban}'
        )
        data = resp.data.get('data', {})
        resp.data = MatchingData(
            is_matched=data.get('matched', False),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def company_information(self, national_id: str) -> Response:
        params = {
            "nationalId": national_id,
        }
        resp = self.collect_api(
            path="/v1/facility/companyInquiry",
            method="POST",
            data=params,
            search_key=f'company-{national_id}'
        )
        data = resp.data.get('data', {})
        resp.data = CompanyInformation(
            national_id=data.get('nationalId', ''),
            title=data.get('companyTitle', ''),
            registration_id=data.get('companyRegistrationId', ''),
            establishment_date=data.get('establishmentDate', ''),
            address=data.get('address', ''),
            postal_code=data.get('postalCode', ''),
            type=data.get('companyType', ''),
            status=data.get('status', ''),
            description=data.get('extraDescription', ''),
            related_people=[
                Person(
                    first_name=person.get('firstName', ''),
                    last_name=person.get('lastName', ''),
                    national_code=person.get('nationalCode', ''),
                    nationality=person.get('nationality', ''),
                    person_type=person.get('personType', ''),
                    position=person.get('officePosition', '')
                )
                for person in data.get('companyRelatedPeople', [])
            ],
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def persian_name_to_english(self, name: str) -> Response:
        params = {
            "persianText": name
        }
        resp = self.collect_api(
            path="/v1/facility/persianToFinglish",
            method="POST",
            data=params,
            search_key=f'persianToEn-{name}'
        )
        data = resp.data.get('data', {})
        resp.data = PersianNameToEnglishData(
            english_name=data.get('finglishText', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp

    def national_card_ocr(self, card_back: str, card_front: str) -> Response:
        params = {
            'nationalCardFront': card_front,
            'nationalCardBack': card_back
        }
        resp = self.collect_api(
            path="/v1/facility/nationalCardOcr",
            method="POST",
            data=params
        )
        data = resp.data.get('data', {})
        resp.data = NationalCard(
            first_name=data.get('firstName', ''),
            last_name=data.get('lastName', ''),
            father_name=data.get('fatherName', ''),
            national_code=data.get('nationalCode', ''),
            birth_date=data.get('birthDate', ''),
            expiration_date=data.get('expirationDate', ''),
            face_photo=data.get('facePhoto', None),
            city=data.get('city', ''),
            province=data.get('province', ''),
            code=ZibalRequester.RESULT_MAP.get(resp.data.get('result', ''), '')
        )
        return resp
