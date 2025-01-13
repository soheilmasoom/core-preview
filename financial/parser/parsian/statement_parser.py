from typing import List

import jdatetime
import xlrd

from accounts.utils.similarity import clean_persian_word
from financial.parser.base_parser import TransactionInfo, ParseError
from financial.parser.parsian.description_parser import parse_parsian_description


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

        balance = row[6] or 0
        ref_id = row[7]
        tracking_id = row[8]
        branch_name = clean_persian_word(row[9])

        data = parse_parsian_description(description) or {}

        transactions.append(
            TransactionInfo(
                created=created,
                deposit_type='d' if deposit_amount else 'w',
                amount=deposit_amount or withdraw_amount,
                reference_number=ref_id,
                tracking_id=tracking_id,
                balance=balance,
                description=description,
                bank_branch=branch_name,
                deposit_number=data.get('deposit_number', ''),
                sender_name=data.get('sender_name', '').replace('*', ' '),
                sender_iban=data.get('sender_iban', ''),
                sender_bank=data.get('sender_bank', ''),
                sender_account=data.get('sender_account', ''),
            )
        )

    return transactions
