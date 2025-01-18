import logging
from datetime import datetime
from typing import List

import requests
from django.utils import timezone

from accounts.verifiers.utils import Response, ServerError
from financial.exceptions import ProviderError
from financial.interface.base_interface import BaseChannel, WithdrawDTO, WalletDTO, WithdrawRefundedDTO
from financial.models.withdraw_request import BaseTransfer
from financial.utils.ach import next_ach_clear_time
from financial.utils.bank import BANK_INFO
from ledger.utils.fields import PENDING, DONE, CANCELED

logger = logging.getLogger(__name__)


class JibitChannel(BaseChannel):
    BASE_URL = 'https://napi.jibit.ir/trf'

    def _get_token(self):
        resp = requests.post(
            url=self.BASE_URL + '/v2/tokens/generate',
            json={
                'apiKey': self.gateway.withdraw_api_key,
                'secretKey': self.gateway.withdraw_api_secret,
            },
            timeout=30,
        )

        if resp.ok:
            resp_data = resp.json()
            return resp_data['accessToken']

    def collect_api(self, path: str, method: str = 'GET', data: dict = None, timeout: float = 30) -> Response:
        url = 'https://napi.jibit.ir/trf' + path
        request_kwargs = {
            'url': url,
            'timeout': timeout,
            'headers': {'Authorization': f'Bearer {self._get_token()}'},
        }

        try:
            if method == 'GET':
                resp = requests.get(params=data, **request_kwargs)
            else:
                method_prop = getattr(requests, method.lower())
                resp = method_prop(json=data, **request_kwargs)
        except requests.exceptions.ConnectionError:
            logger.error('jibit connection error', extra={
                'url': url,
                'method': method,
                'data': data,
            })
            raise TimeoutError

        resp_data = resp.json()

        if self.verbose or not resp.ok:
            print('status', resp.status_code)
            print('data', resp_data)

        return Response(data=resp_data, success=resp.ok, status_code=resp.status_code)

    def get_wallet_data(self) -> WalletDTO:
        resp = self.collect_api('/v2/balances')
        balance = 0
        free = 0

        for d in resp.get_success_data()['balances']:
            balance_type = d['balanceType']

            if balance_type == 'STL':
                free = d['amount']

            balance += d['amount']

        return WalletDTO(
            balance=balance // 10,
            free=free // 10
        )

    def get_instant_banks(self) -> list:
        return []  # instant withdraw disabled

        swift_codes = self._collect_api('/v2/banks/status').data or []

        if not swift_codes:
            return []

        banks = list(map(lambda bank: bank.slug, filter(lambda bank: bank.swift_code in swift_codes, BANK_INFO)))

        if set(banks) != set(self.gateway.instant_withdraw_banks):
            self.gateway.instant_withdraw_banks = banks
            self.gateway.save(update_fields=['instant_withdraw_banks'])

        return banks

    def create_withdraw(self, transfer: BaseTransfer) -> WithdrawDTO:
        if transfer.bank_account.bank in self.get_instant_banks():
            transfer_mode = 'NORMAL'
        else:
            transfer_mode = 'ACH'

        resp = self.collect_api('/v2/transfers', method='POST', data={
            'submissionMode': 'TRANSFER',
            'batchID': 'wr-%s' % transfer.id,
            'transfers': [{
                'transferID': str(transfer.id),
                'destination': transfer.bank_account.iban,
                'destinationFirstName': transfer.bank_account.user.first_name,
                'destinationLastName': transfer.bank_account.user.last_name,
                'amount': transfer.amount,
                'currency': 'TOMAN',
                'cancellable': False,
                'transferMode': transfer_mode,
                'description': 'برداشت کاربر'
            }],
        })

        if not resp.success:
            code = resp.data['errors'][0]['code']
            if code == 'transfer.already_exists':
                return WithdrawDTO(
                    tracking_id='',
                    status=PENDING,
                )

            elif code == 'transfers.0.source_bank.not_supported':
                return WithdrawDTO(
                    tracking_id='',
                    status=CANCELED,
                    message=code,
                )

            else:
                raise ProviderError(code)

        if resp.data.get('submittedCount', 0) == 0:
            raise ProviderError('Jibit submission failed')

        return WithdrawDTO(
            tracking_id='',
            status=PENDING,
            receive_datetime=next_ach_clear_time()
        )

    def get_withdraw_status(self, transfer: BaseTransfer) -> WithdrawDTO:
        resp = self.collect_api('/v2/transfers?transferID={}'.format(transfer.id))
        data = resp.get_success_data()

        mapping_status = {
            'CANCELLED': CANCELED,
            'TRANSFERRED': DONE,
            'CANCELLING': CANCELED,
            'FAILED': CANCELED,
            'IN_PROGRESS': PENDING
        }

        transfer = data['transfers'][0]

        tracking_id = transfer['bankTransferID'] or ''

        channel_status = transfer['state']
        status = mapping_status.get(channel_status, PENDING)

        if tracking_id and status == PENDING:
            status = DONE

        return WithdrawDTO(
            tracking_id=tracking_id,
            status=status,
        )

    def get_refunded_withdraws(self, start: datetime) -> List[WithdrawRefundedDTO]:
        refunds = []
        page_size = 100

        for page in range(1, 21):
            resp = self.collect_api(f'/v2/transfers/filter', data={
                'page': page,
                'size': page_size,
                'state': 'MANUALLY_FAILED',
                'from': start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            })

            data = resp.get_success_data()
            refunds_data = data['elements']

            for d in refunds_data:
                assert d['state'] == 'MANUALLY_FAILED'

                refunds.append(
                    WithdrawRefundedDTO(
                        id=int(d['transferID']),
                        amount=d['amount'] if d['currency'] == 'TOMAN' else d['amount'] // 10,
                        ref_id=d['bankTransferID']
                    )
                )

            if len(refunds_data) < page_size:
                break

        return refunds
