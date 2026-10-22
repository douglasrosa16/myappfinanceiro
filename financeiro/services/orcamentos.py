from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from django.urls import reverse

from financeiro.models import Orcamento
from financeiro.services.dashboard import carregar_contribuicoes_dashboard


ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


def _limites_meses(meses: set[str]) -> tuple[date, date]:
    primeiro = min(meses)
    ultimo = max(meses)
    ano_inicial, mes_inicial = (int(parte) for parte in primeiro.split("-"))
    ano_final, mes_final = (int(parte) for parte in ultimo.split("-"))
    return (
        date(ano_inicial, mes_inicial, 1),
        date(ano_final, mes_final, monthrange(ano_final, mes_final)[1]),
    )


def _categoria_superior_id(categoria, categorias: dict) -> int | None:
    if not categoria:
        return None
    atual = categoria
    visitados = set()
    while atual.categoria_pai_id and atual.categoria_pai_id not in visitados:
        visitados.add(atual.pk)
        atual = categorias.get(atual.categoria_pai_id, atual.categoria_pai)
    return atual.pk


def _chave_contribuicao(contribuicao, categorias: dict) -> tuple[str, int | None, str]:
    if contribuicao.origem == "CONTA":
        competencia = contribuicao.registro.evento.data.strftime("%Y-%m")
        ambito = contribuicao.registro.evento.ambito
    else:
        competencia = contribuicao.registro.vencimento.strftime("%Y-%m")
        ambito = contribuicao.registro.ambito_exibicao
    return competencia, _categoria_superior_id(contribuicao.categoria, categorias), ambito


def _percentual_realizado(realizado: Decimal, limite: Decimal) -> Decimal | None:
    if limite <= ZERO:
        return None
    if realizado <= ZERO:
        return ZERO
    return (realizado / limite * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _faixa_percentual(percentual: Decimal | None) -> str:
    if percentual is None:
        return "neutral"
    if percentual <= Decimal("80.00"):
        return "blue"
    if percentual <= Decimal("90.00"):
        return "orange"
    return "red"


def _urls_detalhamento_categoria(
    mes_referencia: str,
    categoria_id: int,
    ambito: str = "all",
) -> tuple[str, str]:
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))
    data_inicial = date(ano, mes, 1)
    data_final = date(ano, mes, monthrange(ano, mes)[1])
    base = {
        "date_from": data_inicial.strftime("%d/%m/%Y"),
        "date_to": data_final.strftime("%d/%m/%Y"),
        "account": "all",
        "card": "all",
        "origin": "all",
    }
    detalhe = {
        **base,
        "nature": "all",
        "type": "category",
        "value": categoria_id,
    }
    lancamentos = {
        **base,
        "analysis_type": "category",
        "analysis_value": categoria_id,
        "analysis_nature": "all",
        "parent_category": categoria_id,
        "computes": "COMPUTA",
    }
    if ambito != "all":
        detalhe["scope"] = ambito
        lancamentos["analysis_scope"] = ambito
    return (
        f"{reverse('dashboard_detalhamento')}?{urlencode(detalhe)}",
        f"{reverse('eventos')}?{urlencode(lancamentos)}",
    )


def _urls_detalhamento(orcamento: Orcamento) -> tuple[str, str]:
    return _urls_detalhamento_categoria(
        orcamento.mes,
        orcamento.categoria_id,
        orcamento.ambito,
    )


def enriquecer_orcamentos_com_realizado(usuario, orcamentos: list[Orcamento]) -> list[Orcamento]:
    if not orcamentos:
        return orcamentos

    meses = {orcamento.mes for orcamento in orcamentos}
    data_inicial, data_final = _limites_meses(meses)
    dados = carregar_contribuicoes_dashboard(
        usuario,
        date_from=data_inicial,
        date_to=data_final,
    )
    realizados = defaultdict(lambda: ZERO)
    for contribuicao in dados["contribuicoes"]:
        chave = _chave_contribuicao(contribuicao, dados["categorias"])
        if chave[0] in meses:
            realizados[chave] += contribuicao.valor_indicador

    for orcamento in orcamentos:
        chave = (orcamento.mes, orcamento.categoria_id, orcamento.ambito)
        realizado = realizados[chave].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        limite = Decimal(orcamento.limite)
        percentual = _percentual_realizado(realizado, limite)
        orcamento.realizado = realizado
        orcamento.percentual_realizado = percentual
        orcamento.percentual_css = (
            f"{min(max(percentual, ZERO), HUNDRED):.2f}"
            if percentual is not None
            else "0.00"
        )
        orcamento.faixa_percentual = _faixa_percentual(percentual)
        orcamento.detalhe_url, orcamento.lancamentos_url = _urls_detalhamento(orcamento)
    return orcamentos


def resumir_orcamento_dashboard(usuario, mes: str) -> dict:
    orcamentos = list(
        Orcamento.objects.filter(usuario=usuario, mes=mes)
        .select_related("categoria", "categoria__categoria_pai")
        .order_by("categoria__nome", "ambito", "id")
    )
    enriquecer_orcamentos_com_realizado(usuario, orcamentos)

    consolidados = {}
    for orcamento in orcamentos:
        item = consolidados.setdefault(
            orcamento.categoria_id,
            {
                "categoria_id": orcamento.categoria_id,
                "nome": orcamento.categoria.rotulo_com_pai,
                "orcado": ZERO,
                "realizado": ZERO,
            },
        )
        item["orcado"] += Decimal(orcamento.limite)
        item["realizado"] += orcamento.realizado

    total_orcado = sum((item["orcado"] for item in consolidados.values()), ZERO)
    categorias = []
    for item in consolidados.values():
        item["orcado"] = item["orcado"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        item["realizado"] = item["realizado"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        participacao = _percentual_realizado(item["orcado"], total_orcado)
        comprometimento = _percentual_realizado(item["realizado"], item["orcado"])
        item.update(
            {
                "participacao": participacao,
                "participacao_css": (
                    f"{min(max(participacao, ZERO), HUNDRED):.2f}"
                    if participacao is not None
                    else "0.00"
                ),
                "participacao_aria_max": max(participacao or HUNDRED, HUNDRED),
                "percentual_comprometido": comprometimento,
                "percentual_comprometido_css": (
                    f"{min(max(comprometimento, ZERO), HUNDRED):.2f}"
                    if comprometimento is not None
                    else "0.00"
                ),
                "percentual_comprometido_aria_max": max(comprometimento or HUNDRED, HUNDRED),
                "faixa_percentual": _faixa_percentual(comprometimento),
            }
        )
        item["detalhe_url"], item["lancamentos_url"] = _urls_detalhamento_categoria(
            mes,
            item["categoria_id"],
        )
        categorias.append(item)

    categorias.sort(
        key=lambda item: (
            item["percentual_comprometido"] is None,
            -(item["percentual_comprometido"] or ZERO),
            item["nome"].casefold(),
        )
    )
    return {
        "mes": mes,
        "mes_rotulo": f"{mes[5:7]}/{mes[:4]}",
        "total_orcado": total_orcado.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "categorias": categorias,
    }


def alertas_orcamento_dashboard(resumo: dict) -> list[dict]:
    alertas = []
    for categoria in resumo["categorias"]:
        percentual = categoria["percentual_comprometido"]
        if percentual is None or percentual < Decimal("90.00"):
            continue
        if percentual > HUNDRED:
            situacao = "Orçamento estourado"
        elif percentual == HUNDRED:
            situacao = "Limite do orçamento atingido"
        else:
            situacao = "Orçamento próximo do limite"
        alertas.append(
            {
                "tipo": "orcamento",
                "titulo": categoria["nome"],
                "mensagem": f"{situacao} · {percentual:.2f}% comprometido",
                "realizado": categoria["realizado"],
                "orcado": categoria["orcado"],
                "percentual": percentual,
            }
        )
    return alertas
