from __future__ import annotations

from decimal import Decimal

from financeiro.models import Liquidacao, MovimentoConta, Titulo
from financeiro.services.fechamento_faturas import conciliar_pagamento


def conciliar_titulo(
    titulo: Titulo,
    movimento: MovimentoConta,
    valor: Decimal | None = None,
    origem=Liquidacao.Origem.IMPORTACAO,
    chave="",
) -> Liquidacao:
    """Concilia títulos a pagar ou receber com um movimento efetivo."""
    return conciliar_pagamento(
        titulo.usuario,
        titulo.pk,
        movimento.pk,
        valor=abs(valor if valor is not None else movimento.valor),
        origem=origem,
        chave=chave,
    )


def liquidar_titulo(
    titulo: Titulo,
    movimento: MovimentoConta,
    valor: Decimal | None = None,
    chave="",
) -> Liquidacao:
    """Compatibilidade para os pontos antigos de importação.

    Toda baixa agora passa pelo serviço único, que controla rateio do
    movimento, programação e idempotência.
    """
    return conciliar_titulo(titulo, movimento, valor, chave=chave)
