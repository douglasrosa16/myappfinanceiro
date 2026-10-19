from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from financeiro.models import Conta, MovimentoConta, SaldoContaPeriodo, Situacao


ZERO = Decimal("0.00")


def primeiro_dia_mes(valor: date) -> date:
    return valor.replace(day=1)


def proximo_mes(valor: date) -> date:
    if valor.month == 12:
        return date(valor.year + 1, 1, 1)
    return date(valor.year, valor.month + 1, 1)


def _meses(inicio: date, fim: date):
    atual = primeiro_dia_mes(inicio)
    limite = primeiro_dia_mes(fim)
    while atual <= limite:
        yield atual
        atual = proximo_mes(atual)


def _inicio_reprocessamento(conta: Conta, desde: date | None) -> date | None:
    if desde:
        return primeiro_dia_mes(desde)
    primeira_data = (
        MovimentoConta.objects.filter(conta=conta)
        .order_by("data_efetiva", "id")
        .values_list("data_efetiva", flat=True)
        .first()
    )
    candidatos = [valor for valor in (primeira_data, conta.data_saldo_inicial, timezone.localdate()) if valor]
    return primeiro_dia_mes(min(candidatos)) if candidatos else None


def _fim_reprocessamento(conta: Conta, inicio: date) -> date:
    ultima_data = (
        MovimentoConta.objects.filter(conta=conta)
        .order_by("-data_efetiva", "-id")
        .values_list("data_efetiva", flat=True)
        .first()
    )
    ultimo_resumo = (
        SaldoContaPeriodo.objects.filter(conta=conta)
        .order_by("-periodo")
        .values_list("periodo", flat=True)
        .first()
    )
    valores = [inicio, timezone.localdate()]
    if ultima_data:
        valores.append(ultima_data)
    if ultimo_resumo:
        valores.append(ultimo_resumo)
    return primeiro_dia_mes(max(valores))


def _saldo_base(conta: Conta, inicio: date) -> Decimal:
    saldo = ZERO
    referencia = conta.data_saldo_inicial
    if not referencia or referencia < inicio:
        saldo += conta.saldo_inicial

    movimentos = MovimentoConta.objects.filter(
        conta=conta,
        evento__situacao=Situacao.REALIZADO,
        data_efetiva__lt=inicio,
    )
    if referencia:
        movimentos = movimentos.filter(data_efetiva__gte=referencia)
    return saldo + (movimentos.aggregate(total=Sum("valor", default=ZERO))["total"] or ZERO)


def reprocessar_saldo_conta(conta_id: int, desde: date | None = None) -> dict:
    conta = Conta.objects.select_for_update().get(pk=conta_id)
    inicio = _inicio_reprocessamento(conta, desde)
    if not inicio:
        SaldoContaPeriodo.objects.filter(conta=conta).delete()
        return {"conta_id": conta.pk, "periodo_inicio": None, "periodo_fim": None, "quantidade_movimentos": 0, "quantidade_periodos": 0}

    fim = _fim_reprocessamento(conta, inicio)
    fim_exclusivo = proximo_mes(fim)
    movimentos = MovimentoConta.objects.filter(
        conta=conta,
        evento__situacao=Situacao.REALIZADO,
        data_efetiva__gte=inicio,
        data_efetiva__lt=fim_exclusivo,
    )
    decimal_field = DecimalField(max_digits=14, decimal_places=2)
    agrupados = {}
    for item in (
        movimentos.annotate(periodo=TruncMonth("data_efetiva"))
        .values("periodo")
        .annotate(
            entradas=Sum(
                Case(
                    When(valor__gt=ZERO, then=F("valor")),
                    default=Value(ZERO),
                    output_field=decimal_field,
                )
            ),
            saidas=Sum(
                Case(
                    When(valor__lt=ZERO, then=-F("valor")),
                    default=Value(ZERO),
                    output_field=decimal_field,
                )
            ),
            quantidade=Count("id"),
        )
    ):
        periodo = item["periodo"] or inicio
        if hasattr(periodo, "date"):
            periodo = periodo.date()
        agrupados[periodo.replace(day=1)] = item

    saldo = _saldo_base(conta, inicio)
    referencia = conta.data_saldo_inicial
    agora = timezone.now()
    novos = []
    quantidade_movimentos = 0
    for periodo in _meses(inicio, fim):
        if referencia and primeiro_dia_mes(referencia) == periodo:
            saldo += conta.saldo_inicial
        item = agrupados.get(periodo, {})
        entradas = item.get("entradas") or ZERO
        saidas = item.get("saidas") or ZERO
        quantidade = item.get("quantidade") or 0
        saldo += entradas - saidas
        quantidade_movimentos += quantidade
        novos.append(
            SaldoContaPeriodo(
                conta=conta,
                periodo=periodo,
                entradas=entradas,
                saidas=saidas,
                saldo_fechamento=saldo,
                quantidade_movimentos=quantidade,
                criado_em=agora,
                atualizado_em=agora,
            )
        )

    SaldoContaPeriodo.objects.filter(conta=conta, periodo__gte=inicio).delete()
    SaldoContaPeriodo.objects.bulk_create(novos)
    return {
        "conta_id": conta.pk,
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "quantidade_movimentos": quantidade_movimentos,
        "quantidade_periodos": len(novos),
        "saldo_fechamento": saldo,
    }


def saldo_conta_ate(conta: Conta, fim: date) -> Decimal | None:
    referencia = conta.data_saldo_inicial
    if referencia and referencia >= fim:
        return ZERO
    resumo = (
        SaldoContaPeriodo.objects.filter(conta=conta, periodo__lt=fim)
        .order_by("-periodo")
        .values_list("saldo_fechamento", flat=True)
        .first()
    )
    if resumo is not None:
        return resumo
    return None
