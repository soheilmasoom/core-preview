from django.db import migrations
from django.db.models import Sum


def populate_wallet_balances(apps, schema_editor):
    Wallet = apps.get_model('ledger', 'Wallet')
    Trx = apps.get_model('ledger', 'Trx')

    received_dict = dict(Trx.objects.filter(receiver__account__type='s').values('receiver').annotate(amount=Sum('amount')).values_list('receiver', 'amount'))
    sent_dict = dict(Trx.objects.filter(sender__account__type='s').values('sender').annotate(amount=Sum('amount')).values_list('sender', 'amount'))

    for w in Wallet.objects.filter(account__type='s'):
        key = w.id
        w.balance = received_dict.get(key, 0) - sent_dict.get(key, 0)
        w.save(update_fields=['balance'])


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0099_remove_trx_check_ledger_trx_amount_and_more'),
    ]

    operations = [
        migrations.RunPython(
            code=populate_wallet_balances, reverse_code=migrations.RunPython.noop
        )
    ]
