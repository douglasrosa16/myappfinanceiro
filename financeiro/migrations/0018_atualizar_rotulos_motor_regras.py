from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0017_regras_categoria_cadastro"),
    ]

    operations = [
        migrations.AlterField(
            model_name="regracategoria",
            name="versao_motor",
            field=models.CharField(
                choices=[("LEGADO", "Legada — compatibilidade"), ("NOVO", "Nova — em uso")],
                default="NOVO",
                max_length=20,
            ),
        ),
    ]
