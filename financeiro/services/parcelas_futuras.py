from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from decimal import Decimal

from django.utils import timezone

from financeiro.models import Ambito, Cartao, Conta, Fatura, NaturezaEvento, ParcelaCartao, Situacao
from financeiro.services.cartoes_faturas import rotulo_ciclo


ZERO = Decimal("0.00")
CICLO_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ROTULOS_AMBITO = {
    Ambito.NAO_DEFINIDO: "Não definido",
    Ambito.PESSOAL: "Pessoal",
    Ambito.PROFISSIONAL: "Profissional",
}
ROTULOS_SITUACAO = dict(Situacao.choices)


def _ciclo_valido(ciclo: str | None) -> bool:
    return bool(ciclo and CICLO_PATTERN.fullmatch(ciclo))


def _somar_ciclos(ciclo: str, quantidade: int) -> str:
    ano, mes = (int(parte) for parte in ciclo.split("-"))
    indice = ano * 12 + mes - 1 + quantidade
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}"


def _texto_normalizado(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto or "")
    return "".join(caractere for caractere in sem_acentos if not unicodedata.combining(caractere)).upper()


def _parcela_elegivel(parcela: ParcelaCartao, incluir_tarifas=False) -> bool:
    return (
        parcela.natureza_exibicao == NaturezaEvento.DESPESA
        and parcela.numero > 0
        and parcela.total > 1
        and parcela.situacao != Situacao.CANCELADO
        and (incluir_tarifas or "ANUIDADE" not in _texto_normalizado(parcela.descricao_exibicao))
    )


def _origem_valor(parcela: ParcelaCartao) -> str:
    if parcela.situacao == Situacao.PREVISTO and parcela.compra.valor_total_estimado:
        return "estimado"
    return "explicito"


def _nome_pessoa(parcela: ParcelaCartao) -> str:
    if parcela.pessoa_id:
        return parcela.pessoa.nome
    if parcela.pessoa_nome_livre:
        return parcela.pessoa_nome_livre
    evento = parcela.compra.evento
    if evento.pessoa_id:
        return evento.pessoa.nome
    return evento.pessoa_nome_livre or "Pessoa não informada"


def _rotulo_situacao(parcela: ParcelaCartao) -> str:
    if parcela.situacao == Situacao.PREVISTO:
        return "Previsto"
    if parcela.situacao == Situacao.REALIZADO:
        return "Cobrado em fatura"
    return ROTULOS_SITUACAO.get(parcela.situacao, parcela.situacao)


def _resolver_filtros(usuario, ciclo: str | None, conta_id=None, cartao_id=None) -> dict:
    contas = list(Conta.objects.filter(usuario=usuario).order_by("nome", "id"))
    cartoes = list(
        Cartao.objects.filter(usuario=usuario)
        .select_related("conta_pagamento_padrao")
        .order_by("nome", "id")
    )
    ciclos_conhecidos = list(
        Fatura.objects.filter(usuario=usuario)
        .order_by("-ciclo")
        .values_list("ciclo", flat=True)
        .distinct()
    )
    ciclo_padrao = ciclos_conhecidos[0] if ciclos_conhecidos else timezone.localdate().strftime("%Y-%m")
    ciclo_selecionado = ciclo if _ciclo_valido(ciclo) else ciclo_padrao
    if ciclo_selecionado not in ciclos_conhecidos:
        ciclos_conhecidos.append(ciclo_selecionado)
        ciclos_conhecidos.sort(reverse=True)

    conta_selecionada = None
    if conta_id not in (None, "", "all"):
        try:
            conta_pk = int(conta_id)
        except (TypeError, ValueError):
            conta_pk = None
        conta_selecionada = next((conta for conta in contas if conta.pk == conta_pk), None)

    cartoes_compativeis = [
        cartao
        for cartao in cartoes
        if not conta_selecionada or cartao.conta_pagamento_padrao_id == conta_selecionada.pk
    ]
    cartao_selecionado = None
    if cartao_id not in (None, "", "all"):
        try:
            cartao_pk = int(cartao_id)
        except (TypeError, ValueError):
            cartao_pk = None
        cartao_selecionado = next(
            (cartao for cartao in cartoes_compativeis if cartao.pk == cartao_pk),
            None,
        )

    cartoes_filtrados = [cartao_selecionado] if cartao_selecionado else cartoes_compativeis
    return {
        "ciclo_selecionado": ciclo_selecionado,
        "ciclos": [{"valor": valor, "rotulo": rotulo_ciclo(valor)} for valor in ciclos_conhecidos],
        "contas": contas,
        "conta_selecionada": conta_selecionada,
        "cartoes_compativeis": cartoes_compativeis,
        "cartao_selecionado": cartao_selecionado,
        "cartoes_filtrados": cartoes_filtrados,
    }


def contribuicoes_futuras(
    usuario,
    cartoes: list[Cartao],
    ciclo_selecionado: str,
    *,
    incluir_tarifas=False,
) -> list[dict]:
    """Retorna somente parcelas ainda não materializadas em registros explícitos.

    A projeção é compartilhada pelo calendário de parcelas e pelos indicadores de
    limite. Estes últimos optam por incluir tarifas que não aparecem no gráfico.
    """
    cartoes_ids = [cartao.pk for cartao in cartoes]
    if not cartoes_ids:
        return []
    parcelas = list(
        ParcelaCartao.objects.filter(
            compra__usuario=usuario,
            compra__cartao_id__in=cartoes_ids,
        )
        .select_related("compra__evento", "compra__cartao", "fatura__cartao")
        .order_by("compra_id", "fatura__ciclo", "numero", "id")
    )

    grupos = OrderedDict()
    for parcela in parcelas:
        grupos.setdefault(parcela.compra_id, []).append(parcela)

    contribuicoes = OrderedDict()
    for compra_id, registros in grupos.items():
        elegiveis = [
            parcela for parcela in registros
            if _parcela_elegivel(parcela, incluir_tarifas=incluir_tarifas)
        ]
        if not elegiveis:
            continue

        conhecidos = [parcela for parcela in elegiveis if parcela.fatura.ciclo <= ciclo_selecionado]
        ultima = max(conhecidos, key=lambda parcela: (parcela.fatura.ciclo, parcela.numero, parcela.pk), default=None)
        registros_por_numero = {parcela.numero: parcela for parcela in registros}

        if ultima:
            for numero in range(ultima.numero + 1, ultima.total + 1):
                explicita = registros_por_numero.get(numero)
                if explicita:
                    if explicita.fatura.ciclo > ciclo_selecionado and _parcela_elegivel(
                        explicita,
                        incluir_tarifas=incluir_tarifas,
                    ):
                        contribuicoes[(compra_id, numero)] = {
                            "compra_id": compra_id,
                            "cartao_id": explicita.compra.cartao_id,
                            "numero": numero,
                            "ciclo": explicita.fatura.ciclo,
                            "valor": abs(explicita.valor),
                            "origem": _origem_valor(explicita),
                        }
                    continue

                ciclo_projetado = _somar_ciclos(ultima.fatura.ciclo, numero - ultima.numero)
                if ciclo_projetado > ciclo_selecionado:
                    contribuicoes[(compra_id, numero)] = {
                        "compra_id": compra_id,
                        "cartao_id": ultima.compra.cartao_id,
                        "numero": numero,
                        "ciclo": ciclo_projetado,
                        "valor": abs(ultima.valor),
                        "origem": "estimado",
                    }
        else:
            for explicita in elegiveis:
                if explicita.fatura.ciclo <= ciclo_selecionado:
                    continue
                contribuicoes[(compra_id, explicita.numero)] = {
                    "compra_id": compra_id,
                    "cartao_id": explicita.compra.cartao_id,
                    "numero": explicita.numero,
                    "ciclo": explicita.fatura.ciclo,
                    "valor": abs(explicita.valor),
                    "origem": _origem_valor(explicita),
                }

    return list(contribuicoes.values())


def consultar_parcelas_futuras(usuario, ciclo=None, conta_id=None, cartao_id=None) -> dict:
    filtros = _resolver_filtros(usuario, ciclo, conta_id, cartao_id)
    ciclo_selecionado = filtros["ciclo_selecionado"]
    cartoes_filtrados = filtros.pop("cartoes_filtrados")
    contribuicoes = contribuicoes_futuras(usuario, cartoes_filtrados, ciclo_selecionado)

    parcelas = list(
        ParcelaCartao.objects.filter(
            compra__usuario=usuario,
            compra__cartao_id__in=[cartao.pk for cartao in cartoes_filtrados],
            fatura__ciclo=ciclo_selecionado,
        )
        .select_related(
            "compra__evento__pessoa",
            "compra__cartao",
            "fatura__cartao",
            "categoria",
            "pessoa",
        )
        .order_by("compra_id", "fatura__ciclo", "numero", "id")
    )
    grupos = OrderedDict()
    for parcela in parcelas:
        grupos.setdefault(parcela.compra_id, []).append(parcela)
    compras = []
    for compra_id, registros in grupos.items():
        elegiveis = [parcela for parcela in registros if _parcela_elegivel(parcela)]
        ultima = max(elegiveis, key=lambda parcela: (parcela.numero, parcela.pk), default=None)
        if ultima:
            compras.append({
                "compra_id": compra_id,
                "data_original": ultima.data_original_exibicao,
                "descricao": ultima.descricao_exibicao,
                "pessoa": _nome_pessoa(ultima),
                "ambito": ROTULOS_AMBITO.get(
                    ultima.ambito_exibicao,
                    ultima.ambito_exibicao or "Não definido",
                ),
                "cartao": ultima.compra.cartao,
                "ultimo_ciclo": ultima.fatura.ciclo,
                "categoria": ultima.categoria.nome if ultima.categoria_id else "A classificar",
                "situacao": _rotulo_situacao(ultima),
                "numero": ultima.numero,
                "total": ultima.total,
                "valor": abs(ultima.valor),
            })

    total_compras = sum((compra["valor"] for compra in compras), ZERO)

    totais_por_ciclo = {}
    for contribuicao in contribuicoes:
        totais_por_ciclo.setdefault(contribuicao["ciclo"], ZERO)
        totais_por_ciclo[contribuicao["ciclo"]] += contribuicao["valor"]

    maior_total = max(totais_por_ciclo.values(), default=ZERO)
    projecoes = []
    for ciclo_projetado, total in sorted(totais_por_ciclo.items()):
        percentual = ZERO if not maior_total else total / maior_total * Decimal("100")
        projecoes.append(
            {
                "ciclo": ciclo_projetado,
                "total": total,
                "percentual": f"{percentual:.4f}",
            }
        )

    return {
        **filtros,
        "ciclo_rotulo": rotulo_ciclo(ciclo_selecionado),
        "projecoes": projecoes,
        "compras": compras,
        "quantidade_compras": len(compras),
        "total_compras": total_compras,
        "contribuicoes": contribuicoes,
    }
