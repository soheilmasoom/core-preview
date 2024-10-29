from dataclasses import dataclass, asdict
from typing import List, Union

from django.conf import settings


@dataclass
class Bank:
    slug: str
    name: str
    card_prefix: List[str]
    iban_code: str
    swift_code: str = ''

    def as_dict(self):
        return {
            'slug': self.slug,
            'name': self.name,
            'logo': settings.MINIO_STORAGE_STATIC_URL + '/banks/%s.png' % self.slug.lower(),
        }


BANK_INFO = [
    Bank('MELLI', 'بانک ملی', ['603799'], '0170', 'MELIIR'),
    Bank('REFAH', 'بانک رفاه', ['589463'], '0130', 'REFAIR'),
    Bank('RESALAT', 'بانک رسالت', ['504172'], '0700', 'RESBIR'),
    Bank('KESHAVARZI', 'بانک کشاورزی', ['603770'], '0160', 'KESHIR'),
    Bank('TOSEAH_TAAVON', 'بانک توسعه تعاون', ['502908'], '0220', 'TTBIIR'),
    Bank('TOSEAH_SADERAT', 'بانک توسعه صادرات', ['627648'], '0200', 'EDBIIR'),
    Bank('SADERAT', 'بانک صادرات', ['603769'], '0190', 'BSIRIR'),
    Bank('KARAFARIN', 'بانک کارآفرین', ['627488'], '0530', 'KBIDIR'),
    Bank('EGHTESAD_NOVIN', 'بانک اقتصاد نوین', ['627412'], '0550', 'BEGNIR'),
    Bank('SHAHR', 'بانک شهر', ['502806', '504706'], '0610', 'CIYBIR'),
    Bank('SEPAH', 'بانک سپه', ['589210'], '0150', 'SEPBIR'),
    Bank('MEHR_IRAN', 'بانک مهر ایران', ['606373'], '0600', 'MEHRIR'),
    Bank('PASARGAD', 'بانک پاسارگاد', ['502229'], '0570', 'BKBPIR'),
    Bank('NOOR', 'موسسه اعتباری نور', ['507677'], '0800', 'NOORIR'),
    Bank('SARMAYEH', 'بانک سرمایه', ['639607'], '0580', 'SRMBIR'),
    Bank('MELAL', 'موسسه اعتباری ملل', ['606256'], '0750', 'MELLIR'),
    Bank('MASKAN', 'بانک مسکن', ['628023'], '0140', 'BKMNIR'),
    Bank('POST', 'پست بانک ایران', ['627760'], '0210', 'PBIRIR'),
    Bank('KHAVARMIANEH', 'بانک خاورمیانه', ['585947'], '0780', 'KHMIIR'),
    Bank('SINA', 'بانک سینا', ['639346'], '0590', 'SINAIR'),
    Bank('MELLAT', 'بانک ملت', ['610433'], '0120', 'BKMTIR'),
    Bank('IRANZAMIN', 'بانک ایران زمین', ['505785'], '0690', 'IRZAIR'),
    Bank('DAY', 'بانک دی', ['502938'], '0660', 'DAYBIR'),
    Bank('AYANDEH', 'بانک آینده', ['636214'], '0620', 'AYBKIR'),
    Bank('GARDESHGARI', 'بانک گردشگری', ['505416'], '0640', 'TOSMIR'),
    Bank('SAMAN', 'بانک سامان', ['621986'], '0560', 'SABCIR'),
    Bank('TEJARAT', 'بانک تجارت', ['627353', '585983'], '0180', 'BTEJIR'),
    Bank('PARSIAN', 'بانک پارسیان', ['622106'], '0540', 'BKPAIR'),
    Bank('SANAT_VA_MADAN', 'بانک صنعت و معدن', ['627961'], '0110', 'BOIMIR'),
]


def get_bank_code_from_iban(iban: str) -> str:
    return iban[4:8]


def get_bank_from_slug(slug: str) -> Bank:
    return next(filter(lambda bank: bank.slug == slug, BANK_INFO), None)


def get_bank(swift_code: str) -> Bank:
    return next(filter(lambda bank: bank.swift_code == swift_code, BANK_INFO), None)


def get_bank_from_card_pan(card_pan: str) -> Bank:
    prefix = card_pan[:6]
    return next(filter(lambda bank: prefix in bank.card_prefix, BANK_INFO), None)


def get_bank_from_iban(iban: str) -> Bank:
    prefix = iban[4:7]
    return next(filter(lambda bank: bank.iban_code[:3] == prefix, BANK_INFO), None)
