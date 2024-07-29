from django.db import migrations
from ledger.models.trx import Trx as TrxModel
from ledger.models.asset import Asset as AssetModel
from django.db.models import Q

def get_account(apps, sender, receiver):
    Asset = apps.get_model('ledger', 'Asset')
    irt_asset = Asset.objects.get(symbol=AssetModel.IRT)
    return receiver.account if sender.asset == irt_asset else sender.account

def create_convert_dust_trx(apps, convert_dust, group_id):
    Trx = apps.get_model('ledger', 'Trx')
    ConvertDustTrx = apps.get_model('ledger', 'ConvertDustTrx')
    Asset = apps.get_model('ledger', 'Asset')

    irt_asset = Asset.objects.get(symbol=AssetModel.IRT)
    count = Trx.objects.filter(scope=TrxModel.DUST, receiver__asset=irt_asset, group_id=group_id).count()
    for trx in Trx.objects.filter(~Q(sender__asset=irt_asset), scope=TrxModel.DUST, group_id=group_id):
        ConvertDustTrx.objects.create(
            convert_dust=convert_dust,
            asset=trx.sender.asset,
            base_asset=irt_asset,
            amount=trx.amount,
            converted_amount = convert_dust.converted_amount/count,
            )


def data_migration(apps, schema_editor):
    Trx = apps.get_model('ledger', 'Trx')
    ConvertDust = apps.get_model('ledger', 'ConvertDust')
    ConvertDustTrx = apps.get_model('ledger', 'ConvertDustTrx')
    Asset = apps.get_model('ledger', 'Asset')

    ConvertDust.objects.all().delete()
    ConvertDustTrx.objects.all().delete()

    irt_asset = Asset.objects.get(symbol=AssetModel.IRT)
    for trx in Trx.objects.filter(scope=TrxModel.DUST, sender__asset=irt_asset):
        dust = ConvertDust.objects.create(
            created = trx.created,
            account = get_account(apps, trx.sender, trx.receiver),
            base_asset=Asset.objects.get(symbol=AssetModel.IRT),
            converted_amount = trx.amount,
            group_id = trx.group_id,
        )
        create_convert_dust_trx(apps, dust, trx.group_id)

class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0277_alter_marginhistorymodel_amount'),
    ]

    operations = [
        migrations.RunPython(code=data_migration, reverse_code=migrations.RunPython.noop),
    ]