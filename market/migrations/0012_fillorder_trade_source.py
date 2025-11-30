from django.db import migrations, models


def set_source_trade(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('market', '0011_order_market_new_orders_price_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='fillorder',
            name='trade_source',
            field=models.CharField(blank=True, choices=[('otc', 'otc'), (None, 'market'), ('system', 'system')], db_index=True, max_length=8, null=True),
        ),
        migrations.RunPython(
            code=set_source_trade, reverse_code=migrations.RunPython.noop
        ),
    ]
