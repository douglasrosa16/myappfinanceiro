from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0007_fechamento_pagamento_transportes"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventofinanceiro",
            name="pessoa_nome_livre",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="pessoa_nome_livre",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
