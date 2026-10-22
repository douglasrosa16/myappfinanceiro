from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from financeiro.models import Ambito, NaturezaEvento, RegraCategoria, RegraCategoriaCondicao
from financeiro.ofx import normalize_text


NATUREZAS_FORA_DO_MOTOR = {
    NaturezaEvento.PAGAMENTO_FATURA,
    NaturezaEvento.TRANSFERENCIA,
}


@dataclass(frozen=True)
class ConjuntoRegrasCategoria:
    novas: tuple[RegraCategoria, ...]
    legadas: tuple[RegraCategoria, ...]


@dataclass(frozen=True)
class DadosClassificacao:
    descricao: str
    observacao: str
    valor: Decimal | None
    natureza: str
    origem: str
    conta_id: int | None
    cartao_id: int | None


@dataclass(frozen=True)
class ResultadoRegraCategoria:
    regra: RegraCategoria | None
    campos_aplicados: frozenset[str]


@dataclass(frozen=True)
class ResultadoSugestaoManual:
    regra: RegraCategoria | None
    condicoes_correspondentes: int = 0


def carregar_regras_categoria(usuario) -> ConjuntoRegrasCategoria:
    regras = list(
        RegraCategoria.objects.filter(usuario=usuario, ativa=True)
        .select_related("categoria", "pessoa")
        .prefetch_related("condicoes")
    )
    novas = tuple(
        sorted(
            (regra for regra in regras if regra.versao_motor == RegraCategoria.VersaoMotor.NOVO),
            key=lambda regra: (regra.prioridade, regra.pk),
        )
    )
    legadas = tuple(
        sorted(
            (regra for regra in regras if regra.versao_motor == RegraCategoria.VersaoMotor.LEGADO),
            key=lambda regra: regra.pk,
        )
    )
    return ConjuntoRegrasCategoria(novas=novas, legadas=legadas)


def dados_item_importacao(item) -> DadosClassificacao:
    valor = item.valor_final
    return DadosClassificacao(
        descricao=item.descricao_final or "",
        observacao=item.observacao or "",
        valor=abs(valor) if valor is not None else None,
        natureza=item.natureza or "",
        origem=item.importacao.origem,
        conta_id=item.importacao.conta_id,
        cartao_id=item.importacao.cartao_id,
    )


def _comparar_texto(atual: str, esperado: str, operador: str) -> bool:
    atual = normalize_text(atual)
    esperado = normalize_text(esperado)
    if operador == RegraCategoriaCondicao.Operador.CONTEM:
        return esperado in atual
    if operador == RegraCategoriaCondicao.Operador.NAO_CONTEM:
        return esperado not in atual
    if operador == RegraCategoriaCondicao.Operador.IGUAL:
        return atual == esperado
    if operador == RegraCategoriaCondicao.Operador.DIFERENTE:
        return atual != esperado
    if operador == RegraCategoriaCondicao.Operador.COMECA_COM:
        return atual.startswith(esperado)
    if operador == RegraCategoriaCondicao.Operador.TERMINA_COM:
        return atual.endswith(esperado)
    return False


def _comparar_valor(atual: Decimal | None, esperado: str, operador: str) -> bool:
    if atual is None:
        return False
    try:
        esperado_decimal = abs(Decimal(esperado))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if operador == RegraCategoriaCondicao.Operador.IGUAL:
        return atual == esperado_decimal
    if operador == RegraCategoriaCondicao.Operador.DIFERENTE:
        return atual != esperado_decimal
    if operador == RegraCategoriaCondicao.Operador.MAIOR:
        return atual > esperado_decimal
    if operador == RegraCategoriaCondicao.Operador.MAIOR_IGUAL:
        return atual >= esperado_decimal
    if operador == RegraCategoriaCondicao.Operador.MENOR:
        return atual < esperado_decimal
    if operador == RegraCategoriaCondicao.Operador.MENOR_IGUAL:
        return atual <= esperado_decimal
    return False


def _comparar_escolha(atual, esperado: str, operador: str) -> bool:
    if atual in (None, ""):
        return False
    atual = str(atual)
    esperado = str(esperado)
    if operador == RegraCategoriaCondicao.Operador.IGUAL:
        return atual == esperado
    if operador == RegraCategoriaCondicao.Operador.DIFERENTE:
        return atual != esperado
    return False


def condicao_corresponde(condicao: RegraCategoriaCondicao, dados: DadosClassificacao) -> bool:
    if condicao.campo == RegraCategoriaCondicao.Campo.DESCRICAO:
        return _comparar_texto(dados.descricao, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.OBSERVACAO:
        return _comparar_texto(dados.observacao, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.VALOR:
        return _comparar_valor(dados.valor, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.NATUREZA:
        return _comparar_escolha(dados.natureza, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.ORIGEM:
        return _comparar_escolha(dados.origem, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.CONTA:
        return _comparar_escolha(dados.conta_id, condicao.valor, condicao.operador)
    if condicao.campo == RegraCategoriaCondicao.Campo.CARTAO:
        return _comparar_escolha(dados.cartao_id, condicao.valor, condicao.operador)
    return False


def regra_nova_corresponde(regra: RegraCategoria, dados: DadosClassificacao) -> bool:
    condicoes = list(regra.condicoes.all())
    if not condicoes:
        return False
    resultados = [condicao_corresponde(condicao, dados) for condicao in condicoes]
    if regra.combinador == RegraCategoria.Combinador.QUALQUER:
        return any(resultados)
    return all(resultados)


def _condicao_tem_dado_disponivel(condicao: RegraCategoriaCondicao, dados: DadosClassificacao) -> bool:
    if condicao.campo == RegraCategoriaCondicao.Campo.DESCRICAO:
        return bool(normalize_text(dados.descricao))
    if condicao.campo == RegraCategoriaCondicao.Campo.OBSERVACAO:
        return bool(normalize_text(dados.observacao))
    if condicao.campo == RegraCategoriaCondicao.Campo.VALOR:
        return dados.valor is not None
    if condicao.campo == RegraCategoriaCondicao.Campo.NATUREZA:
        return bool(dados.natureza)
    if condicao.campo == RegraCategoriaCondicao.Campo.ORIGEM:
        return bool(dados.origem)
    if condicao.campo == RegraCategoriaCondicao.Campo.CONTA:
        return dados.conta_id is not None
    if condicao.campo == RegraCategoriaCondicao.Campo.CARTAO:
        return dados.cartao_id is not None
    return False


def pontuar_regra_manual(regra: RegraCategoria, dados: DadosClassificacao) -> int | None:
    correspondentes = 0
    for condicao in regra.condicoes.all():
        if not _condicao_tem_dado_disponivel(condicao, dados):
            continue
        corresponde = condicao_corresponde(condicao, dados)
        if corresponde:
            correspondentes += 1
        elif regra.combinador == RegraCategoria.Combinador.TODAS:
            return None
    return correspondentes or None


def melhor_regra_manual(
    dados: DadosClassificacao,
    conjunto: ConjuntoRegrasCategoria,
) -> ResultadoSugestaoManual:
    if dados.natureza in NATUREZAS_FORA_DO_MOTOR:
        return ResultadoSugestaoManual(regra=None)

    candidatas = []
    for regra in conjunto.novas:
        pontuacao = pontuar_regra_manual(regra, dados)
        if pontuacao is not None:
            candidatas.append((pontuacao, regra))
    if candidatas:
        pontuacao, regra = min(
            candidatas,
            key=lambda candidata: (
                -candidata[0],
                candidata[1].prioridade,
                candidata[1].pk,
            ),
        )
        return ResultadoSugestaoManual(regra=regra, condicoes_correspondentes=pontuacao)

    descricao = normalize_text(dados.descricao)
    if descricao:
        for regra in conjunto.legadas:
            texto = normalize_text(regra.texto)
            if texto and texto in descricao:
                return ResultadoSugestaoManual(regra=regra, condicoes_correspondentes=1)
    return ResultadoSugestaoManual(regra=None)


def primeira_regra_correspondente(
    dados: DadosClassificacao,
    conjunto: ConjuntoRegrasCategoria,
) -> RegraCategoria | None:
    if dados.natureza in NATUREZAS_FORA_DO_MOTOR:
        return None
    for regra in conjunto.novas:
        if regra_nova_corresponde(regra, dados):
            return regra
    descricao = normalize_text(dados.descricao)
    for regra in conjunto.legadas:
        texto = normalize_text(regra.texto)
        if texto and texto in descricao:
            return regra
    return None


def aplicar_resultados_regra(
    item,
    regra: RegraCategoria,
    *,
    campos_protegidos: set[str] | frozenset[str] | None = None,
) -> frozenset[str]:
    protegidos = set(campos_protegidos or ())
    aplicados = set()
    usuario_id = item.importacao.usuario_id

    if (
        "categoria" not in protegidos
        and item.categoria_id is None
        and regra.categoria_id
        and regra.categoria.usuario_id == usuario_id
    ):
        item.categoria = regra.categoria
        aplicados.add("categoria")
    if (
        "pessoa" not in protegidos
        and item.pessoa_id is None
        and regra.pessoa_id
        and regra.pessoa.usuario_id == usuario_id
    ):
        item.pessoa = regra.pessoa
        aplicados.add("pessoa")
    if (
        "ambito" not in protegidos
        and item.ambito in {None, "", Ambito.NAO_DEFINIDO}
        and regra.ambito in {Ambito.PESSOAL, Ambito.PROFISSIONAL}
    ):
        item.ambito = regra.ambito
        aplicados.add("ambito")
    if (
        regra.versao_motor == RegraCategoria.VersaoMotor.NOVO
        and "natureza" not in protegidos
        and regra.natureza_sugerida
        and item.natureza != regra.natureza_sugerida
    ):
        item.natureza = regra.natureza_sugerida
        aplicados.add("natureza")
    return frozenset(aplicados)


def avaliar_e_aplicar_regra(
    item,
    conjunto: ConjuntoRegrasCategoria,
    *,
    campos_protegidos: set[str] | frozenset[str] | None = None,
) -> ResultadoRegraCategoria:
    regra = primeira_regra_correspondente(dados_item_importacao(item), conjunto)
    if not regra:
        return ResultadoRegraCategoria(regra=None, campos_aplicados=frozenset())
    campos = aplicar_resultados_regra(item, regra, campos_protegidos=campos_protegidos)
    return ResultadoRegraCategoria(regra=regra, campos_aplicados=campos)
