import uuid
from typing import List

import jdatetime
import xlrd
from django.utils import timezone

from financial.parser.base_parser import TransactionInfo, ParseError
from financial.parser.parsian.description_parser import parse_parsian_description, TransactionDescriptionInfo


def parse_parsian_statement(statement) -> List[TransactionInfo]:
    workbook = xlrd.open_workbook(file_contents=statement)

    sheet = workbook.sheets()[0]

    transactions = []

    for row_idx in range(6, sheet.nrows):
        row = [cell.value for cell in sheet.row(row_idx)]

        if not row[0]:
            break

        description = row[1]
        created_jalali = row[2] + ' ' + row[3]
        created = jdatetime.datetime.strptime(created_jalali, '%Y/%m/%d %H:%M:%S').togregorian().astimezone()

        deposit_amount = row[4] or 0
        withdraw_amount = row[5] or 0

        if deposit_amount and withdraw_amount:
            raise ParseError(f'Row {row_idx}: both of deposit and withdraw amounts are present')

        if not deposit_amount and not withdraw_amount:
            raise ParseError(f'Row {row_idx}: none of deposit and withdraw amounts are present')

        balance = (row[6] or 0) // 10
        bank_reference_number = row[7]

        deposit_type = TransactionInfo.DEPOSIT if deposit_amount else TransactionInfo.WITHDRAW
        if deposit_type != TransactionInfo.DEPOSIT:
            continue

        amount = (deposit_amount or withdraw_amount) // 10

        try:
            description_info = parse_parsian_description(description)
        except ParseError:
            description_info = TransactionDescriptionInfo(
                bank_transaction_id='',
                sender_identifier='',
                record_type='',
                receiver_identifier=''
            )

        account_iban = sheet.row(2)[4].value
        ref_number = uuid.uuid5(uuid.NAMESPACE_DNS, f"{bank_reference_number}-{deposit_type}-{amount}-{balance}-{description}")

        transactions.append(
            TransactionInfo(
                reference_number=str(ref_number),
                account_iban=account_iban,
                bank_reference_number=bank_reference_number,
                bank_transaction_id=description_info.bank_transaction_id,
                amount=amount,
                deposit_type=deposit_type,
                balance=balance,
                created=timezone.now(),
                deposited_at=created,
                deposit_number='',
                raw_data=description,
                sender_identifier=description_info.sender_identifier,
                sender_iban='',
                sender_name='',
                record_type=description_info.record_type,
                receiver_iban=account_iban,
                kyt_passed=False,
            )
        )

    return transactions
