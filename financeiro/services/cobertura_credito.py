from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch, Q

from financeiro.models import (
    Categoria,
    CompraCartao,
    Conta,
    EventoFinanceiro,
    Liquidacao,
    MovimentoConta,
    NaturezaEvento,
    ParcelaCartao,
    ProgramacaoPagamento,
    Situacao,
    Titulo,
)


ZERO = Decimal("0.00")
HUNDRED = Decimal("100")
NATUREZAS = {"all", "personal", "business"}


def _categoria_compativel(categoria: Categoria | None, natureza: str) -> bool:
    if natureza == "all":
        return True
    if not categoria:
        return False
    if natureza == "personal":
        return categoria.natureza in {Categoria.Natureza.PESSOAL, Categoria.Natureza.AMBOS}
    return categoria.natureza in {Categoria.Natureza.EMPRESARIAL, Categoria.Natureza.AMBOS}


def _proporcao_rateios(evento: EventoFinanceiro | None, natureza: str) -> Decimal:
    if natureza == "all":
        return Decimal("1")
    if not evento:
        return ZERO
    rateios = list(evento.rateios.all())
    total = sum((abs(item.valor) for item in rateios), ZERO)
    if total <= ZERO:
        return ZERO
    compativel = sum(
        (abs(item.valor) for item in rateios if _categoria_compativel(item.categoria, natureza)),
        ZERO,
    )
    return min(compativel / total, Decimal("1"))


def _natureza_parcela(parcela: ParcelaCartao) -> str:
    return parcela.natureza_exibicao


def _valor_assinado_cartao(valor: Decimal, natureza_evento: str) -> Decimal:
    if natureza_evento == NaturezaEvento.DESPESA:
        return abs(valor)
    if natureza_evento in {NaturezaEvento.ESTORNO, NaturezaEvento.RECEITA}:
        return -abs(valor)
    return ZERO


def _proporcao_parcelas(parcelas: list[ParcelaCartao], natureza: str) -> Decimal:
    if natureza == "all":
        return Decimal("1")
    elegiveis = [
        parcela
        for parcela in parcelas
        if parcela.situacao != Situacao.CANCELADO
        and _natureza_parcela(parcela) not in {NaturezaEvento.PAGAMENTO_FATURA, NaturezaEvento.TRANSFERENCIA}
    ]
    total = sum((abs(parcela.valor) for parcela in elegiveis), ZERO)
    if total <= ZERO:
        return ZERO
    compativel = sum(
        (
            abs(parcela.valor)
            for parcela in elegiveis
            if _categoria_compativel(parcela.categoria, natureza)
        ),
        ZERO,
    )
    return min(compativel / total, Decimal("1"))


def _proporcao_titulo(titulo: Titulo, natureza: str) -> Decimal:
    if natureza == "all":
        return Decimal("1")
    if titulo.evento_id:
        return _proporcao_rateios(titulo.evento, natureza)
    if titulo.fatura_id:
        return _proporcao_parcelas(list(titulo.fatura.parcelas.all()), natureza)
    return ZERO


def _proporcao_movimento(
    movimento: MovimentoConta,
    natureza: str,
    titulos_por_movimento: dict[int, list[Titulo]],
) -> Decimal:
    if natureza == "all":
        return Decimal("1")
    proporcao_evento = _proporcao_rateios(movimento.evento, natureza)
    if proporcao_evento > ZERO:
        return proporcao_evento
    titulos = titulos_por_movimento.get(movimento.pk, [])
    if not titulos:
        return ZERO
    proporcoes = [_proporcao_titulo(titulo, natureza) for titulo in titulos]
    return max(proporcoes, default=ZERO)


def _percentual_cobertura(recursos: Decimal, pressao: Decimal) -> Decimal | None:
    if pressao <= ZERO:
        return None
    return (recursos / pressao * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _estado_trajetoria(primeira_data: date | None, saldo_final: Decimal) -> dict:
    if primeira_data is None:
        return {"codigo": "COBERTO", "rotulo": "Coberto"}
    if saldo_final < ZERO:
        return {"codigo": "DEPENDENCIA_FECHAMENTO", "rotulo": "Dependência no fechamento"}
    return {"codigo": "DEPENDENCIA_TEMPORARIA", "rotulo": "Dependência temporária"}


def _categoria_superior(
    categoria: Categoria | None,
    categorias: dict[int, Categoria],
) -> Categoria | None:
    if not categoria:
        return None
    atual = categoria
    visitados = set()
    while atual.categoria_pai_id and atual.categoria_pai_id not in visitados:
        visitados.add(atual.pk)
        categoria_pai = categorias.get(atual.categoria_pai_id)
        atual = categoria_pai if categoria_pai is not None else atual.categoria_pai
    return atual


def _valores_categoria_rateios(
    evento: EventoFinanceiro | None,
    natureza: str,
) -> list[tuple[Categoria | None, Decimal]]:
    if not evento:
        return []
    return [
        (rateio.categoria, abs(rateio.valor))
        for rateio in evento.rateios.all()
        if _categoria_compativel(rateio.categoria, natureza)
    ]


def _parcelas_elegiveis(parcelas: list[ParcelaCartao]) -> list[ParcelaCartao]:
    return [
        parcela
        for parcela in parcelas
        if parcela.situacao != Situacao.CANCELADO
        and _natureza_parcela(parcela) not in {
            NaturezaEvento.PAGAMENTO_FATURA,
            NaturezaEvento.TRANSFERENCIA,
        }
    ]


def _valores_categoria_parcelas(
    parcelas: list[ParcelaCartao],
    natureza: str,
    *,
    assinados: bool = False,
) -> list[tuple[Categoria | None, Decimal]]:
    valores = []
    for parcela in _parcelas_elegiveis(parcelas):
        if not _categoria_compativel(parcela.categoria, natureza):
            continue
        valor = (
            _valor_assinado_cartao(parcela.valor, _natureza_parcela(parcela))
            if assinados
            else abs(parcela.valor)
        )
        if valor != ZERO:
            valores.append((parcela.categoria, valor))
    return valores


def _valores_categoria_titulo(
    titulo: Titulo,
    natureza: str,
) -> list[tuple[Categoria | None, Decimal]]:
    valores = _valores_categoria_rateios(titulo.evento, natureza)
    if valores:
        return valores
    if titulo.fatura_id:
        return _valores_categoria_parcelas(list(titulo.fatura.parcelas.all()), natureza)
    return []


def _componentes_categoria(
    valores_categoria: list[tuple[Categoria | None, Decimal]],
    valor_total: Decimal,
    categorias: dict[int, Categoria],
) -> list[dict]:
    valor_total = valor_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if valor_total == ZERO:
        return []

    agrupados: dict[int | None, dict] = {}
    for categoria, valor in valores_categoria:
        if valor == ZERO:
            continue
        chave = categoria.pk if categoria else None
        item = agrupados.setdefault(chave, {"categoria": categoria, "valor": ZERO})
        item["valor"] += valor

    soma = sum((item["valor"] for item in agrupados.values()), ZERO)
    if not agrupados or soma == ZERO or (soma > ZERO) != (valor_total > ZERO):
        agrupados = {None: {"categoria": None, "valor": valor_total}}
        soma = valor_total

    fator = valor_total / soma
    itens_ordenados = sorted(
        agrupados.values(),
        key=lambda item: (
            (item["categoria"].nome.casefold() if item["categoria"] else ""),
            item["categoria"].pk if item["categoria"] else 0,
        ),
    )
    componentes = []
    acumulado = ZERO
    for indice, item in enumerate(itens_ordenados):
        categoria = item["categoria"]
        if indice == len(itens_ordenados) - 1:
            valor = valor_total - acumulado
        else:
            valor = (item["valor"] * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            acumulado += valor
        superior = _categoria_superior(categoria, categorias)
        componentes.append(
            {
                "categoria_id": categoria.pk if categoria else None,
                "categoria_nome": categoria.nome if categoria else "A classificar",
                "categoria_superior_id": superior.pk if superior else None,
                "categoria_superior_nome": superior.nome if superior else "A classificar",
                "computa_resultado": categoria.computa_resultado if categoria else None,
                "nao_computa_resultado": bool(categoria and not categoria.computa_resultado),
                "valor": valor,
            }
        )
    return componentes


def _componentes_por_pesos(
    pesos_categoria: list[tuple[Categoria | None, Decimal]],
    valor_total: Decimal,
    categorias: dict[int, Categoria],
) -> list[dict]:
    sinal = Decimal("1") if valor_total >= ZERO else Decimal("-1")
    valores = [(categoria, abs(valor) * sinal) for categoria, valor in pesos_categoria]
    return _componentes_categoria(valores, valor_total, categorias)


def _assinar_pesos_categoria(
    pesos_categoria: list[tuple[Categoria | None, Decimal]],
    valor_total: Decimal,
) -> list[tuple[Categoria | None, Decimal]]:
    sinal = Decimal("1") if valor_total >= ZERO else Decimal("-1")
    return [(categoria, abs(valor) * sinal) for categoria, valor in pesos_categoria]


def _item(
    *,
    data: date,
    descricao: str,
    origem: str,
    origem_nome: str,
    situacao: str,
    valor: Decimal,
    estimado: bool = False,
    observacao: str = "",
    evento_id: int | None = None,
    registro_id: int | None = None,
    componentes_categoria: list[dict] | None = None,
    compoe_composicao_categoria: bool = True,
) -> dict:
    return {
        "data": data,
        "descricao": descricao,
        "origem": origem,
        "origem_nome": origem_nome,
        "situacao": situacao,
        "valor": valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "estimado": estimado,
        "observacao": observacao,
        "evento_id": evento_id or 0,
        "registro_id": registro_id or 0,
        "componentes_categoria": componentes_categoria or [],
        "compoe_composicao_categoria": compoe_composicao_categoria,
    }


def _movimentos_realizados(
    usuario,
    contas: list[Conta],
    inicio: date,
    fim_exclusivo: date,
    natureza: str,
    categorias: dict[int, Categoria],
) -> tuple[list[dict], list[dict]]:
    contas_ids = [conta.pk for conta in contas]
    if not contas_ids:
        return [], []
    movimentos = list(
        MovimentoConta.objects.filter(
            conta_id__in=contas_ids,
            conta__usuario=usuario,
            evento__situacao=Situacao.REALIZADO,
            evento__data__gte=inicio,
            evento__data__lt=fim_exclusivo,
        )
        .exclude(evento__natureza=NaturezaEvento.TRANSFERENCIA)
        .select_related("conta", "evento")
        .prefetch_related("evento__rateios__categoria")
        .order_by("evento__data", "id")
    )
    liquidacoes = list(
        Liquidacao.objects.filter(
            movimento_conta_id__in=[movimento.pk for movimento in movimentos],
            status=Liquidacao.Status.ATIVA,
        )
        .select_related("titulo__evento", "titulo__fatura")
        .prefetch_related(
            "titulo__evento__rateios__categoria",
            "titulo__fatura__parcelas__categoria",
            "titulo__fatura__parcelas__compra__evento",
        )
    )
    titulos_por_movimento: dict[int, list[Titulo]] = defaultdict(list)
    for liquidacao in liquidacoes:
        if liquidacao.movimento_conta_id:
            titulos_por_movimento[liquidacao.movimento_conta_id].append(liquidacao.titulo)

    receitas = []
    saidas = []
    for movimento in movimentos:
        proporcao = _proporcao_movimento(movimento, natureza, titulos_por_movimento)
        if proporcao <= ZERO:
            continue
        valor = (abs(movimento.valor) * proporcao).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        evento = movimento.evento
        pesos_categoria = _valores_categoria_rateios(evento, natureza)
        if not pesos_categoria:
            pesos_categoria = [
                valor_categoria
                for titulo in titulos_por_movimento.get(movimento.pk, [])
                for valor_categoria in _valores_categoria_titulo(titulo, natureza)
            ]
        if evento.natureza == NaturezaEvento.RECEITA and movimento.valor > ZERO:
            componentes = _componentes_por_pesos(pesos_categoria, valor, categorias)
            receitas.append(
                _item(
                    data=evento.data,
                    descricao=evento.descricao,
                    origem="CONTA",
                    origem_nome=movimento.conta.nome,
                    situacao="Realizado",
                    valor=valor,
                    evento_id=evento.pk,
                    registro_id=movimento.pk,
                    componentes_categoria=componentes,
                )
            )
        elif evento.natureza == NaturezaEvento.ESTORNO and movimento.valor > ZERO:
            componentes = _componentes_por_pesos(pesos_categoria, -valor, categorias)
            saidas.append(
                _item(
                    data=evento.data,
                    descricao=evento.descricao,
                    origem="CONTA",
                    origem_nome=movimento.conta.nome,
                    situacao="Realizado",
                    valor=-valor,
                    observacao="Estorno que reduz as saídas do período.",
                    evento_id=evento.pk,
                    registro_id=movimento.pk,
                    componentes_categoria=componentes,
                )
            )
        elif movimento.valor < ZERO:
            componentes = _componentes_por_pesos(pesos_categoria, valor, categorias)
            saidas.append(
                _item(
                    data=evento.data,
                    descricao=evento.descricao,
                    origem="CONTA",
                    origem_nome=movimento.conta.nome,
                    situacao="Realizado",
                    valor=valor,
                    evento_id=evento.pk,
                    registro_id=movimento.pk,
                    componentes_categoria=componentes,
                    compoe_composicao_categoria=evento.natureza
                    != NaturezaEvento.PAGAMENTO_FATURA,
                )
            )
    return receitas, saidas


def _titulos_previstos(
    usuario,
    contas: list[Conta],
    cartoes_ids: set[int],
    inicio: date,
    fim_exclusivo: date,
    natureza: str,
    categorias: dict[int, Categoria],
) -> tuple[list[dict], list[dict]]:
    contas_ids = {conta.pk for conta in contas}
    if not contas_ids:
        return [], []
    parcelas_prefetch = Prefetch(
        "fatura__parcelas",
        queryset=ParcelaCartao.objects.select_related("categoria", "compra__evento").exclude(
            situacao=Situacao.CANCELADO
        ),
    )
    titulos = list(
        Titulo.objects.filter(
            usuario=usuario,
            ativo=True,
            status=Titulo.Status.ABERTO,
            saldo_aberto__gt=ZERO,
            conta_id__in=contas_ids,
        )
        .filter(Q(fatura__isnull=True) | Q(fatura__cartao_id__in=cartoes_ids))
        .select_related("conta", "evento", "fatura__cartao")
        .prefetch_related(
            "programacoes__conta",
            "evento__rateios__categoria",
            parcelas_prefetch,
        )
        .order_by("vencimento", "id")
    )
    receitas = []
    saidas = []
    for titulo in titulos:
        proporcao = _proporcao_titulo(titulo, natureza)
        if proporcao <= ZERO:
            continue
        programado = ZERO
        destinos = receitas if titulo.tipo == Titulo.Tipo.RECEBER else saidas
        situacao = "Previsto"
        origem_nome = titulo.conta.nome if titulo.conta else "Conta não informada"
        pesos_categoria = _valores_categoria_titulo(titulo, natureza)
        for programacao in titulo.programacoes.all():
            if programacao.status not in {
                ProgramacaoPagamento.Status.ATIVA,
                ProgramacaoPagamento.Status.PARCIAL,
            }:
                continue
            restante = min(
                max(programacao.valor_programado - programacao.valor_realizado, ZERO),
                max(titulo.saldo_aberto - programado, ZERO),
            )
            if restante <= ZERO:
                continue
            programado += restante
            if programacao.conta_id not in contas_ids or not (inicio <= programacao.data_programada < fim_exclusivo):
                continue
            valor_item = restante * proporcao
            destinos.append(
                _item(
                    data=programacao.data_programada,
                    descricao=f"{titulo.descricao} (programado)",
                    origem="TITULO",
                    origem_nome=programacao.conta.nome,
                    situacao=situacao,
                    valor=valor_item,
                    observacao="Saldo ainda aberto do título.",
                    evento_id=titulo.evento_id or titulo.pk,
                    registro_id=programacao.pk,
                    compoe_composicao_categoria=not titulo.fatura_id,
                    componentes_categoria=_componentes_por_pesos(
                        pesos_categoria,
                        valor_item,
                        categorias,
                    ),
                )
            )
        residual = max(titulo.saldo_aberto - programado, ZERO)
        if residual > ZERO and inicio <= titulo.vencimento < fim_exclusivo:
            valor_item = residual * proporcao
            destinos.append(
                _item(
                    data=titulo.vencimento,
                    descricao=titulo.descricao,
                    origem="TITULO",
                    origem_nome=origem_nome,
                    situacao=situacao,
                    valor=valor_item,
                    observacao="Saldo ainda aberto do título.",
                    evento_id=titulo.evento_id or titulo.pk,
                    registro_id=titulo.pk,
                    compoe_composicao_categoria=not titulo.fatura_id,
                    componentes_categoria=_componentes_por_pesos(
                        pesos_categoria,
                        valor_item,
                        categorias,
                    ),
                )
            )
    return receitas, saidas


def _valor_compra(
    compra: CompraCartao,
    natureza: str,
) -> tuple[Decimal, bool, list[tuple[Categoria | None, Decimal]]]:
    todas_parcelas = list(compra.parcelas.all())
    parcelas = _parcelas_elegiveis(todas_parcelas)
    numeros = {parcela.numero for parcela in todas_parcelas if parcela.numero > 0}
    materializada = bool(compra.total_parcelas and len(numeros) >= compra.total_parcelas)
    if materializada:
        valores_categoria = _valores_categoria_parcelas(
            todas_parcelas,
            natureza,
            assinados=True,
        )
        valor = sum((valor for _, valor in valores_categoria), ZERO)
        return valor, False, valores_categoria

    proporcao = _proporcao_parcelas(parcelas, natureza)
    if proporcao <= ZERO:
        proporcao = _proporcao_rateios(compra.evento, natureza)
    if proporcao <= ZERO:
        return ZERO, bool(compra.valor_total_estimado or compra.valor_total is None), []

    pesos_categoria = _valores_categoria_parcelas(parcelas, natureza)
    if not pesos_categoria:
        pesos_categoria = _valores_categoria_rateios(compra.evento, natureza)

    natureza_evento = compra.evento.natureza
    if compra.valor_total is not None and not compra.valor_total_estimado:
        valor = _valor_assinado_cartao(compra.valor_total, natureza_evento) * proporcao
        return valor, False, _assinar_pesos_categoria(pesos_categoria, valor)

    valores_conhecidos = [
        _valor_assinado_cartao(parcela.valor, _natureza_parcela(parcela))
        for parcela in parcelas
    ]
    if not valores_conhecidos:
        valor_base = compra.valor_total or ZERO
        valor = _valor_assinado_cartao(valor_base, natureza_evento) * proporcao
        return valor, True, _assinar_pesos_categoria(pesos_categoria, valor)
    media = sum(valores_conhecidos, ZERO) / Decimal(len(valores_conhecidos))
    quantidade = compra.total_parcelas or len(valores_conhecidos)
    valor = media * Decimal(quantidade) * proporcao
    return valor, True, _assinar_pesos_categoria(pesos_categoria, valor)


def resolver_componentes_compra(
    compra: CompraCartao,
    natureza: str,
    categorias: dict[int, Categoria],
) -> tuple[Decimal, bool, list[dict]]:
    """Resolve uma compra integral com a mesma regra usada pela cobertura.

    O retorno público permite que outras análises por data da compra reutilizem
    a estimativa e a distribuição exatas da cobertura, sem reinterpretar
    parcelas, rateios, estornos ou categorias sem classificação.
    """
    valor, estimado, valores_categoria = _valor_compra(compra, natureza)
    return (
        valor,
        estimado,
        _componentes_categoria(valores_categoria, valor, categorias),
    )


def _compras_cartao(
    usuario,
    cartoes_ids: set[int],
    inicio: date,
    fim_exclusivo: date,
    natureza: str,
    categorias: dict[int, Categoria],
) -> list[dict]:
    if not cartoes_ids:
        return []
    compras = list(
        CompraCartao.objects.filter(
            usuario=usuario,
            cartao_id__in=cartoes_ids,
            data_compra__gte=inicio,
            data_compra__lt=fim_exclusivo,
        )
        .exclude(evento__situacao=Situacao.CANCELADO)
        .select_related("cartao", "evento")
        .prefetch_related(
            "evento__rateios__categoria",
            "parcelas__categoria",
            "parcelas__fatura",
        )
        .order_by("data_compra", "id")
    )
    itens = []
    for compra in compras:
        if compra.evento.natureza in {NaturezaEvento.PAGAMENTO_FATURA, NaturezaEvento.TRANSFERENCIA}:
            continue
        valor, estimado, componentes_categoria = resolver_componentes_compra(
            compra,
            natureza,
            categorias,
        )
        if valor == ZERO:
            continue
        situacao = "Realizado" if compra.evento.situacao == Situacao.REALIZADO else "Previsto"
        itens.append(
            _item(
                data=compra.data_compra,
                descricao=compra.estabelecimento or compra.evento.descricao,
                origem="CARTAO",
                origem_nome=compra.cartao.nome,
                situacao=situacao,
                valor=valor,
                estimado=estimado,
                observacao=(
                    f"Compra reconhecida integralmente no mês ({compra.total_parcelas} parcela(s))."
                ),
                evento_id=compra.evento_id,
                registro_id=compra.pk,
                componentes_categoria=componentes_categoria,
            )
        )
    return itens


def _resumir(itens: list[dict]) -> dict:
    realizados = sum((item["valor"] for item in itens if item["situacao"] == "Realizado"), ZERO)
    previstos = sum((item["valor"] for item in itens if item["situacao"] != "Realizado"), ZERO)
    return {
        "realizados": realizados,
        "previstos": previstos,
        "total": realizados + previstos,
        "itens": itens,
    }


def _percentual_categoria(valor: Decimal, total: Decimal) -> Decimal:
    if total <= ZERO:
        return ZERO
    return (max(valor, ZERO) / total * HUNDRED).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _formatar_composicao_categoria(
    codigo: str,
    rotulo: str,
    itens: list[dict],
) -> dict:
    total = sum((item["valor"] for item in itens), ZERO)
    grupos: dict[int | None, dict] = {}
    for item in itens:
        chave_lancamento = (
            item["origem"],
            item["evento_id"],
            item["registro_id"],
            item["data"],
        )
        for componente in item["componentes_categoria"]:
            chave_superior = componente["categoria_superior_id"]
            grupo = grupos.setdefault(
                chave_superior,
                {
                    "categoria_id": chave_superior,
                    "nome": componente["categoria_superior_nome"],
                    "valor": ZERO,
                    "registros": set(),
                    "subcategorias": {},
                },
            )
            grupo["valor"] += componente["valor"]
            grupo["registros"].add(chave_lancamento)

            chave_categoria = componente["categoria_id"]
            nome_categoria = componente["categoria_nome"]
            if chave_categoria is not None and chave_categoria == chave_superior:
                nome_categoria = "Direto na categoria"
            subcategoria = grupo["subcategorias"].setdefault(
                chave_categoria,
                {
                    "categoria_id": chave_categoria,
                    "nome": nome_categoria,
                    "computa_resultado": componente["computa_resultado"],
                    "nao_computa_resultado": componente["nao_computa_resultado"],
                    "valor": ZERO,
                    "registros": set(),
                    "lancamentos": [],
                },
            )
            subcategoria["valor"] += componente["valor"]
            subcategoria["registros"].add(chave_lancamento)
            subcategoria["lancamentos"].append(
                {
                    "data": item["data"],
                    "descricao": item["descricao"],
                    "origem": item["origem"],
                    "origem_rotulo": {
                        "CONTA": "Conta",
                        "TITULO": "Obrigação",
                        "CARTAO": "Compra no cartão",
                    }.get(item["origem"], item["origem"]),
                    "origem_nome": item["origem_nome"],
                    "situacao": item["situacao"],
                    "valor": componente["valor"],
                    "estimado": item["estimado"],
                    "observacao": item["observacao"],
                    "compra_cartao": item["origem"] == "CARTAO",
                    "evento_id": item["evento_id"],
                    "registro_id": item["registro_id"],
                }
            )

    categorias_formatadas = []
    for grupo in grupos.values():
        subcategorias = []
        for subcategoria in grupo["subcategorias"].values():
            subcategoria["lancamentos"].sort(
                key=lambda item: (
                    item["data"],
                    item["evento_id"],
                    item["origem"],
                    item["registro_id"],
                )
            )
            subcategoria["total_registros"] = len(subcategoria.pop("registros"))
            subcategorias.append(subcategoria)
        subcategorias.sort(key=lambda item: (-item["valor"], item["nome"].casefold()))
        percentual = _percentual_categoria(grupo["valor"], total)
        grupo["percentual"] = percentual
        grupo["percentual_css"] = min(max(percentual, ZERO), HUNDRED)
        grupo["total_registros"] = len(grupo.pop("registros"))
        grupo["subcategorias"] = subcategorias
        categorias_formatadas.append(grupo)
    categorias_formatadas.sort(key=lambda item: (-item["valor"], item["nome"].casefold()))
    return {
        "codigo": codigo,
        "rotulo": rotulo,
        "total": total,
        "total_registros": len(itens),
        "categorias": categorias_formatadas,
    }


def _composicao_categorias(
    receitas: list[dict],
    saidas: list[dict],
    compras: list[dict],
) -> list[dict]:
    saidas_por_competencia = [
        item for item in saidas if item["compoe_composicao_categoria"]
    ]
    return [
        _formatar_composicao_categoria("RECEITAS", "Receitas", receitas),
        _formatar_composicao_categoria(
            "DESPESAS",
            "Despesas",
            saidas_por_competencia + compras,
        ),
    ]


def _evolucao_diaria(
    inicio: date,
    fim: date,
    saldo_inicial: Decimal,
    receitas: list[dict],
    saidas: list[dict],
    compras: list[dict],
) -> dict:
    por_data = defaultdict(lambda: {"receitas": ZERO, "saidas": ZERO, "compras": ZERO})
    for item in receitas:
        por_data[item["data"]]["receitas"] += item["valor"]
    for item in saidas:
        por_data[item["data"]]["saidas"] += item["valor"]
    for item in compras:
        por_data[item["data"]]["compras"] += item["valor"]

    saldo_renda = ZERO
    saldo_com_saldo = saldo_inicial
    primeira_renda = inicio if saldo_renda < ZERO else None
    primeira_com_saldo = inicio if saldo_com_saldo < ZERO else None
    menor_renda = min(saldo_renda, ZERO)
    menor_com_saldo = min(saldo_com_saldo, ZERO)
    linhas = []
    data_atual = inicio
    while data_atual <= fim:
        valores = por_data.get(data_atual)
        if valores:
            saldo_renda += valores["receitas"] - valores["saidas"] - valores["compras"]
            saldo_com_saldo += valores["receitas"] - valores["saidas"] - valores["compras"]
            if saldo_renda < ZERO and primeira_renda is None:
                primeira_renda = data_atual
            if saldo_com_saldo < ZERO and primeira_com_saldo is None:
                primeira_com_saldo = data_atual
            menor_renda = min(menor_renda, saldo_renda)
            menor_com_saldo = min(menor_com_saldo, saldo_com_saldo)
            linhas.append(
                {
                    "data": data_atual,
                    **valores,
                    "saldo_renda": saldo_renda,
                    "saldo_com_saldo": saldo_com_saldo,
                }
            )
        data_atual += timedelta(days=1)
    return {
        "linhas": linhas,
        "saldo_final_renda": saldo_renda,
        "saldo_final_com_saldo": saldo_com_saldo,
        "primeira_data_renda": primeira_renda,
        "primeira_data_com_saldo": primeira_com_saldo,
        "maior_deficit_renda": abs(min(menor_renda, ZERO)),
        "maior_deficit_com_saldo": abs(min(menor_com_saldo, ZERO)),
    }


def consultar_cobertura_credito(
    usuario,
    *,
    data_inicial: date,
    data_final: date,
    contas: list[Conta],
    cartoes: list,
    saldo_inicial: Decimal,
    natureza: str = "all",
) -> dict:
    natureza = natureza if natureza in NATUREZAS else "all"
    fim_exclusivo = data_final + timedelta(days=1)
    cartoes_ids = {cartao.pk for cartao in cartoes}
    categorias = {
        categoria.pk: categoria
        for categoria in Categoria.objects.filter(usuario=usuario).select_related("categoria_pai")
    }
    receitas_realizadas, saidas_realizadas = _movimentos_realizados(
        usuario,
        contas,
        data_inicial,
        fim_exclusivo,
        natureza,
        categorias,
    )
    receitas_previstas, saidas_previstas = _titulos_previstos(
        usuario,
        contas,
        cartoes_ids,
        data_inicial,
        fim_exclusivo,
        natureza,
        categorias,
    )
    compras = _compras_cartao(
        usuario,
        cartoes_ids,
        data_inicial,
        fim_exclusivo,
        natureza,
        categorias,
    )
    receitas = _resumir(receitas_realizadas + receitas_previstas)
    saidas = _resumir(saidas_realizadas + saidas_previstas)
    compras_resumo = _resumir(compras)
    cobertura_renda = receitas["total"] - saidas["total"] - compras_resumo["total"]
    cobertura_com_saldo = saldo_inicial + cobertura_renda
    pressao = saidas["total"] + compras_resumo["total"]
    evolucao = _evolucao_diaria(
        data_inicial,
        data_final,
        saldo_inicial,
        receitas["itens"],
        saidas["itens"],
        compras_resumo["itens"],
    )
    return {
        "data_inicial": data_inicial,
        "data_final": data_final,
        "saldo_inicial": saldo_inicial,
        "receitas": receitas,
        "saidas": saidas,
        "compras_cartao": compras_resumo,
        "pressao_financeira": pressao,
        "cobertura_renda": cobertura_renda,
        "cobertura_com_saldo": cobertura_com_saldo,
        "percentual_cobertura_renda": _percentual_cobertura(receitas["total"], pressao),
        "percentual_cobertura_com_saldo": _percentual_cobertura(
            saldo_inicial + receitas["total"],
            pressao,
        ),
        "primeira_data_dependencia_renda": evolucao["primeira_data_renda"],
        "primeira_data_dependencia_com_saldo": evolucao["primeira_data_com_saldo"],
        "maior_deficit_renda": evolucao["maior_deficit_renda"],
        "maior_deficit_com_saldo": evolucao["maior_deficit_com_saldo"],
        "estado_renda": _estado_trajetoria(
            evolucao["primeira_data_renda"],
            cobertura_renda,
        ),
        "estado_com_saldo": _estado_trajetoria(
            evolucao["primeira_data_com_saldo"],
            cobertura_com_saldo,
        ),
        "composicao_categorias": _composicao_categorias(
            receitas["itens"],
            saidas["itens"],
            compras_resumo["itens"],
        ),
        "evolucao_diaria": evolucao["linhas"],
        "tem_estimativas": any(item["estimado"] for item in compras),
    }
