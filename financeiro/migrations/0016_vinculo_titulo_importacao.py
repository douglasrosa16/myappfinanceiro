from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0015_lancamentos_recorrentes"),
    ]

    operations = [
        migrations.CreateModel(
            name="VinculoTituloImportacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=14)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="titulos_multiplos", to="financeiro.itemimportacao")),
                ("liquidacao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.liquidacao")),
                ("titulo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vinculos_importacao_multipla", to="financeiro.titulo")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="vinculotituloimportacao",
            constraint=models.UniqueConstraint(fields=("item", "titulo"), name="uniq_vinculo_importacao_titulo"),
        ),
        migrations.AddIndex(
            model_name="vinculotituloimportacao",
            index=models.Index(fields=["item", "titulo"], name="financeiro__item_id_9d1265_idx"),
        ),
        migrations.AddIndex(
            model_name="vinculotituloimportacao",
            index=models.Index(fields=["titulo", "liquidacao"], name="financeiro__titulo__fe15c5_idx"),
        ),
    ]
