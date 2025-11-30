from django.db import migrations

from financial.utils.bank import get_bank_from_card_pan, get_bank_from_iban


def populate_bank(apps, schema_editor):
    BankCard = apps.get_model('financial', 'BankCard')
    BankAccount = apps.get_model('financial', 'BankAccount')

    for b in BankCard.objects.all():
        bank = get_bank_from_card_pan(b.card_pan)
        if bank:
            b.bank = bank.slug
        else:
            b.bank = ''

        b.save()

    for b in BankAccount.objects.all():
        bank = get_bank_from_iban(b.iban)

        if bank:
            b.bank_name = bank.slug
        else:
            b.bank_name = ''

        b.save()


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0056_investment_hedged'),
    ]

    operations = [
        migrations.RunPython(
            code=populate_bank, reverse_code=migrations.RunPython.noop
        ),
        migrations.RenameField(
            model_name='bankaccount',
            old_name='bank_name',
            new_name='bank',
        ),
        migrations.RenameField(
            model_name='historicalbankaccount',
            old_name='bank_name',
            new_name='bank',
        ),
    ]
