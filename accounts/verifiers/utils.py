from dataclasses import dataclass
from typing import Union

from django.utils.baseconv import base64


class ServerError(Exception):
    pass


@dataclass
class MatchingData:
    is_matched: bool
    code: str


@dataclass
class CardInfoData:
    owner_name: str
    code: str
    bank_name: str = ''
    card_type: str = ''
    deposit_number: str = ''
    card_pan: str = ''


@dataclass
class IBANInfoData:
    bank_name: str
    owners: list
    code: str
    deposit_number: str = ''
    deposit_status: str = ''


@dataclass
class NationalIdentityData:
    is_matched: bool
    first_name: str
    last_name: str
    father_name: str
    is_alive: bool
    code: str


@dataclass
class CardToIBANData:
    owner_name: str
    IBAN: str
    bank_name: str
    code: str


@dataclass
class Address:
    province: str
    town: str
    district: str
    street: str
    street2: str
    number: int
    floor: str
    side_floor: str
    building_name: str
    description: str


@dataclass
class PostalToAddressData:
    address: Address
    code: str


@dataclass
class CardToAccountData:
    owner_name: str
    bank_name: str
    bank_account: str
    code: str


@dataclass
class Person:
    first_name: str
    last_name: str
    national_code: str
    nationality: str
    person_type: str
    position: str


@dataclass
class CompanyInformation:
    national_id: str
    title: str
    registration_id: str
    establishment_date: str
    address: str
    postal_code: str
    type: str
    status: str
    description: str
    related_people: list
    code: str


@dataclass
class PersianNameToEnglishData:
    english_name: str
    code: str


@dataclass
class NationalCard:
    first_name: str
    last_name: str
    father_name: str
    national_code: str
    birth_date: str
    expiration_date: str
    face_photo: base64
    city: str
    province: str
    code: str


@dataclass
class Request:
    path: str
    method: str
    data: dict = None


@dataclass
class Response:
    data: Union[
        dict, list, None,
        MatchingData,
        CardInfoData,
        IBANInfoData,
        NationalIdentityData,
        CardToIBANData,
        NationalCard,
        Address,
        CardToAccountData,
        PostalToAddressData,
        PersianNameToEnglishData,
        CompanyInformation,
        Person,
    ]
    success: bool = True
    status_code: int = 200

    def get_success_data(self, err: str = None):
        if not self.success:
            raise ServerError(err)

        return self.data

    @property
    def ok(self):
        return 200 <= self.status_code < 400
