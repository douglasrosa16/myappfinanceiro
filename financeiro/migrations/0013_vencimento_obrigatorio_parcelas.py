from calendar import monthrange
from datetime import date
import re

import django.core.validators
from django.db import migrations, models


CICLO_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _partes_ciclo(ciclo):
    correspondencia = CICLO_PATTERN.fullmatch(str(ciclo or ""))
    if not correspondencia:
        return None
    return int(correspondencia.group(1)), int(correspondencia.group(2))


def preencher_vencimentos(apps, schema_editor):
    Cartao = apps.get_model("financeiro", "Cartao")
    Fatura = apps.get_model("financeiro", "Fatura")
    ParcelaCartao = apps.get_model("financeiro", "ParcelaCartao")
    alias = schema_editor.connection.alias

    cartoes_invalidos = list(
        Cartao.objects.using(alias)
        .filter(models.Q(dia_vencimento__isnull=True) | models.Q(dia_vencimento__lt=1) | models.Q(dia_vencimento__gt=31))
        .values_list("pk", flat=True)
    )
    if cartoes_invalidos:
        raise RuntimeError(
            "A migração não pode inferir o dia de vencimento dos cartões: "
            + ", ".join(str(pk) for pk in cartoes_invalidos)
            + ". Corrija esses cadastros antes de executar novamente."
        )

    faturas_invalidas = []
    for fatura in Fatura.objects.using(alias).exclude(vencimento__isnull=True).iterator():
        partes = _partes_ciclo(fatura.ciclo)
        if not partes or (fatura.vencimento.year, fatura.vencimento.month) != partes:
            faturas_invalidas.append(fatura.pk)
    if faturas_invalidas:
        raise RuntimeError(
            "Existem faturas cujo vencimento não pertence ao ciclo informado: "
            + ", ".join(str(pk) for pk in faturas_invalidas)
            + ". Corrija essas faturas antes de executar novamente."
        )

    ciclos_invalidos = []
    atualizacoes = []
    parcelas = (
        ParcelaCartao.objects.using(alias)
        .select_related("fatura__cartao")
        .order_by("pk")
    )
    for parcela in parcelas.iterator():
        partes = _partes_ciclo(parcela.fatura.ciclo)
        if not partes:
            ciclos_invalidos.append(parcela.fatura_id)
            continue
        if parcela.fatura.vencimento:
            vencimento = parcela.fatura.vencimento
        else:
            ano, mes = partes
            dia = min(parcela.fatura.cartao.dia_vencimento, monthrange(ano, mes)[1])
            vencimento = date(ano, mes, dia)
        parcela.vencimento = vencimento
        atualizacoes.append(parcela)

    if ciclos_invalidos:
        raise RuntimeError(
            "Existem faturas com ciclo inválido vinculadas a parcelas: "
            + ", ".join(str(pk) for pk in sorted(set(ciclos_invalidos)))
            + ". Corrija os ciclos antes de executar novamente."
        )
    if atualizacoes:
        ParcelaCartao.objects.using(alias).bulk_update(atualizacoes, ["vencimento"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0012_saldo_conta_periodo"),
    ]

    operations = [
        migrations.RunPython(preencher_vencimentos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="cartao",
            name="dia_vencimento",
            field=models.PositiveSmallIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(31),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="cartao",
            constraint=models.CheckConstraint(
                condition=models.Q(("dia_vencimento__gte", 1), ("dia_vencimento__lte", 31)),
                name="cartao_dia_vencimento_valido",
            ),
        ),
        migrations.AlterField(
            model_name="parcelacartao",
            name="vencimento",
            field=models.DateField(db_index=True),
        ),
    ]
