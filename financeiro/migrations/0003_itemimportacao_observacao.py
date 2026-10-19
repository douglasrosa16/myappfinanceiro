from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0002_importacao_ofx_completa")]

    operations = [
        migrations.AddField(
            model_name="itemimportacao",
            name="observacao",
            field=models.TextField(blank=True),
        ),
    ]
