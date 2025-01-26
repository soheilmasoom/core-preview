from abc import ABC, abstractmethod
from datetime import datetime

from accounts.models import User
from accounts.verifiers.utils import Response


class VerificationService(ABC):
    def __init__(self, user: User):
        self._user = user

    @abstractmethod
    def matching(self, phone_number: str = None, national_code: str = None,
                 full_name: str = None, birth_date: datetime = None,
                 card_pan: str = None, iban: str = None) -> Response:
        pass

    @abstractmethod
    def get_iban_info(self, iban: str) -> Response:
        pass

    @abstractmethod
    def get_card_info(self, card_pan: str) -> Response:
        pass
