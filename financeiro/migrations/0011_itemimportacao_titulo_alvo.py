from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0010_categoria_classificacao_resultado"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemimportacao",
            name="titulo_alvo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_importacao_vinculados",
                to="financeiro.titulo",
            ),
        ),
    ]
