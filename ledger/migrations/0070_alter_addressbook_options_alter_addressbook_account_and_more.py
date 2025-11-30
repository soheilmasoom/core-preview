
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0027_alter_historicaluser_national_code_duplicated_alert_and_more'),
        ('ledger', '0069_merge_20220406_1054'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='addressbook',
            options={'verbose_name': 'دفترچه آدرس\u200cها', 'verbose_name_plural': 'دفترچه\u200cهای آدرس'},
        ),
        migrations.AlterField(
            model_name='addressbook',
            name='account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.account', verbose_name='کاربر'),
        ),
        migrations.AlterField(
            model_name='addressbook',
            name='address',
            field=models.CharField(max_length=100, verbose_name='آدرس'),
        ),
        migrations.AlterField(
            model_name='addressbook',
            name='asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='ledger.asset', verbose_name='رمزارز'),
        ),
        migrations.AlterField(
            model_name='addressbook',
            name='name',
            field=models.CharField(max_length=100, verbose_name='نام'),
        ),
        migrations.AlterField(
            model_name='addressbook',
            name='network',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ledger.network', verbose_name='شبکه'),
        ),
    ]
