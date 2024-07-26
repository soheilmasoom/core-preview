from django.db import migrations
from ledger.models.trx import Trx as TrxModel
from ledger.models.asset import Asset as AssetModel

def data_migration(apps, schema_editor):
    Trx = apps.get_model('ledger', 'Trx')
    Dust = apps.get_model('ledger', 'Dust')
    Asset = apps.get_model('ledger', 'Asset')

    dusts = []
    for trx in Trx.objects.filter(scope=TrxModel.DUST):
        dusts.append(
            Dust(
                created = trx.created,
                sender = trx.sender,
                receiver = trx.receiver,
                amount = trx.amount,
                base_asset=Asset.objects.get(symbol=AssetModel.IRT),
                converted_amount = 0,
                group_id = trx.group_id,
            )
        )
        Dust.objects.all().delete()
        Dust.objects.bulk_create(dusts)

class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0276_dust_dust_ledger_dust_sender_created_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(data_migration),
    ]