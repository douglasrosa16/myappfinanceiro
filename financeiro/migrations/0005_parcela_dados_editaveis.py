import django.db.models.deletion
from django.db import migrations, models


def preencher_dados_das_parcelas(apps, schema_editor):
    parcela_model = apps.get_model("financeiro", "ParcelaCartao")
    rateio_model = apps.get_model("financeiro", "RateioCategoria")
    for parcela in parcela_model.objects.select_related("compra__evento").iterator():
        evento = parcela.compra.evento
        categoria_id = (
            rateio_model.objects.filter(evento_id=evento.pk)
            .order_by("id")
            .values_list("categoria_id", flat=True)
            .first()
        )
        parcela_model.objects.filter(pk=parcela.pk).update(
            natureza=evento.natureza,
            descricao=evento.descricao,
            data_original=parcela.compra.data_compra,
            vencimento=evento.vencimento,
            categoria_id=categoria_id,
            pessoa_id=evento.pessoa_id,
            ambito=evento.ambito,
        )


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0004_itemimportacao_revisado_em")]

    operations = [
        migrations.AddField(
            model_name="parcelacartao",
            name="ambito",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PESSOAL", "Pessoal"),
                    ("PROFISSIONAL", "Profissional"),
                    ("NAO_DEFINIDO", "Nao definido"),
                ],
                default="",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="categoria",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="financeiro.categoria",
            ),
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="data_original",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="descricao",
            field=models.CharField(blank=True, default="", max_length=220),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="natureza",
            field=models.CharField(
                blank=True,
                choices=[
                    ("DESPESA", "Despesa"),
                    ("RECEITA", "Receita"),
                    ("ESTORNO", "Estorno"),
                    ("PAGAMENTO_FATURA", "Pagamento de fatura"),
                    ("TRANSFERENCIA", "Transferencia"),
                ],
                default="",
                max_length=30,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="pessoa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="financeiro.pessoa",
            ),
        ),
        migrations.AddField(
            model_name="parcelacartao",
            name="vencimento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(preencher_dados_das_parcelas, migrations.RunPython.noop),
    ]
