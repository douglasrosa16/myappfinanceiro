import django.db.models.deletion
from datetime import date
from decimal import Decimal
from django.db import migrations, models


def preencher_saldos(apps, schema_editor):
    conta_model = apps.get_model("financeiro", "Conta")
    movimento_model = apps.get_model("financeiro", "MovimentoConta")
    resumo_model = apps.get_model("financeiro", "SaldoContaPeriodo")
    zero = Decimal("0.00")

    for conta in conta_model.objects.all().iterator():
        datas = [date.today().replace(day=1)]
        if conta.data_saldo_inicial:
            datas.append(conta.data_saldo_inicial)
        primeira = (
            movimento_model.objects.filter(conta_id=conta.pk)
            .order_by("data_efetiva", "id")
            .values_list("data_efetiva", flat=True)
            .first()
        )
        ultima = (
            movimento_model.objects.filter(conta_id=conta.pk)
            .order_by("-data_efetiva", "-id")
            .values_list("data_efetiva", flat=True)
            .first()
        )
        if primeira:
            datas.append(primeira)
        inicio = min(valor.replace(day=1) for valor in datas)
        fim = max((ultima or inicio).replace(day=1), date.today().replace(day=1))
        referencia = conta.data_saldo_inicial
        saldo = conta.saldo_inicial if not referencia or referencia < inicio else zero
        movimentos_anteriores = movimento_model.objects.filter(
            conta_id=conta.pk,
            evento__situacao="REALIZADO",
            data_efetiva__lt=inicio,
        )
        if referencia:
            movimentos_anteriores = movimentos_anteriores.filter(data_efetiva__gte=referencia)
        saldo += movimentos_anteriores.aggregate(total=models.Sum("valor"))["total"] or zero

        periodo = inicio
        while periodo <= fim:
            proximo = date(periodo.year + (periodo.month == 12), 1 if periodo.month == 12 else periodo.month + 1, 1)
            if referencia and referencia.replace(day=1) == periodo:
                saldo += conta.saldo_inicial
            movimentos = movimento_model.objects.filter(
                conta_id=conta.pk,
                evento__situacao="REALIZADO",
                data_efetiva__gte=periodo,
                data_efetiva__lt=proximo,
            )
            if referencia:
                movimentos = movimentos.filter(data_efetiva__gte=referencia)
            entradas = zero
            saidas = zero
            quantidade = 0
            for movimento in movimentos.iterator():
                quantidade += 1
                if movimento.valor > zero:
                    entradas += movimento.valor
                else:
                    saidas += abs(movimento.valor)
            saldo += entradas - saidas
            resumo_model.objects.create(
                conta_id=conta.pk,
                periodo=periodo,
                entradas=entradas,
                saidas=saidas,
                saldo_fechamento=saldo,
                quantidade_movimentos=quantidade,
            )
            periodo = proximo


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0011_itemimportacao_titulo_alvo"),
    ]

    operations = [
        migrations.CreateModel(
            name="SaldoContaPeriodo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("periodo", models.DateField()),
                ("entradas", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("saidas", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("saldo_fechamento", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("quantidade_movimentos", models.PositiveIntegerField(default=0)),
                (
                    "conta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saldos_periodo",
                        to="financeiro.conta",
                    ),
                ),
            ],
            options={
                "ordering": ["conta_id", "periodo"],
            },
        ),
        migrations.AddConstraint(
            model_name="saldocontaperiodo",
            constraint=models.UniqueConstraint(
                fields=("conta", "periodo"),
                name="uniq_saldo_conta_periodo",
            ),
        ),
        migrations.AddIndex(
            model_name="saldocontaperiodo",
            index=models.Index(fields=["conta", "periodo"], name="financeiro_saldo_conta_periodo_idx"),
        ),
        migrations.RunPython(preencher_saldos, migrations.RunPython.noop),
    ]
