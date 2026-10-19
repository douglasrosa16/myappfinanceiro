from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from financeiro.models import (
    AplicacaoLiquidacaoProgramacao,
    Conta,
    EventoFinanceiro,
    Fatura,
    FechamentoFatura,
    HistoricoFatura,
    ItemFechamentoFatura,
    Liquidacao,
    MovimentoConta,
    NaturezaEvento,
    ParcelaCartao,
    ProgramacaoPagamento,
    SaldoTransportadoFatura,
    Situacao,
    Titulo,
)
from financeiro.services.saldo_contas import reprocessar_saldo_conta
from financeiro.vencimentos_cartao import VencimentoCartaoInvalido, validar_vencimento_no_ciclo


ZERO = Decimal("0.00")


def _registrar(fatura: Fatura, evento: str, descricao: str, valor=ZERO, **dados) -> None:
    HistoricoFatura.objects.create(
        fatura=fatura,
        evento=evento,
        descricao=descricao,
        valor=valor,
        dados=dados,
    )


def _validar_titulo_operavel(titulo: Titulo) -> None:
    if titulo.fatura_id and titulo.fatura.status not in {Fatura.Status.FECHADA, Fatura.Status.PARCIAL}:
        raise ValidationError("Feche a fatura antes de programar, conciliar ou movimentar o saldo.")


def _valores_confirmados(fatura: Fatura):
    parcelas = list(
        ParcelaCartao.objects.select_for_update()
        .filter(fatura=fatura, situacao=Situacao.REALIZADO)
        .select_related("compra__evento")
    )
    pendencias = ParcelaCartao.objects.filter(
        fatura=fatura, situacao__in=[Situacao.PREVISTO, Situacao.PENDENTE]
    ).count()
    bruto = sum(
        (p.valor for p in parcelas if p.natureza_exibicao == NaturezaEvento.DESPESA), ZERO
    )
    creditos = sum(
        (p.valor for p in parcelas if p.natureza_exibicao in {NaturezaEvento.ESTORNO, NaturezaEvento.RECEITA}),
        ZERO,
    )
    return parcelas, pendencias, bruto, creditos, bruto - creditos


def _atualizar_titulo(titulo: Titulo) -> Titulo:
    """Atualiza o cache de saldo a partir do livro de liquidações e transportes."""
    liquidado = titulo.liquidacoes.filter(status=Liquidacao.Status.ATIVA).aggregate(
        valor=Sum("valor", default=ZERO)
    )["valor"] or ZERO
    transportado = titulo.transportes_saida.filter(
        status__in=[SaldoTransportadoFatura.Status.CONFIRMADO, SaldoTransportadoFatura.Status.INCORPORADO]
    ).aggregate(valor=Sum("valor", default=ZERO))["valor"] or ZERO
    saldo = titulo.valor_original - liquidado - transportado
    if saldo < ZERO:
        raise ValidationError("Liquidações e transportes não podem superar o valor do título.")
    titulo.valor_transportado = transportado
    titulo.saldo_aberto = saldo
    if saldo > ZERO:
        titulo.ativo = True
        titulo.status = Titulo.Status.ABERTO
    elif liquidado >= titulo.valor_original:
        titulo.ativo = False
        titulo.status = Titulo.Status.LIQUIDADO
    else:
        titulo.ativo = False
        titulo.status = Titulo.Status.SUSPENSO
    titulo.save(update_fields=["valor_transportado", "saldo_aberto", "ativo", "status", "atualizado_em"])

    if titulo.fatura_id:
        fatura = titulo.fatura
        if titulo.status == Titulo.Status.LIQUIDADO:
            fatura.status = Fatura.Status.PAGA
        elif saldo > ZERO and (liquidado > ZERO or transportado > ZERO):
            fatura.status = Fatura.Status.PARCIAL
        elif fatura.status != Fatura.Status.ABERTA:
            fatura.status = Fatura.Status.FECHADA
        fatura.save(update_fields=["status", "atualizado_em"])
    return titulo


def recalcular_titulo(titulo: Titulo) -> Titulo:
    """Recalcula saldo e status para fluxos externos de conciliação/estorno."""
    return _atualizar_titulo(titulo)


def saldo_programado(titulo: Titulo) -> Decimal:
    return titulo.programacoes.filter(
        status__in=[ProgramacaoPagamento.Status.ATIVA, ProgramacaoPagamento.Status.PARCIAL]
    ).aggregate(
        valor=Sum("valor_programado", default=ZERO) - Sum("valor_realizado", default=ZERO)
    )["valor"] or ZERO


@transaction.atomic
def fechar_fatura(usuario, fatura_id: int, vencimento: date, conta: Conta | None = None, observacao="") -> Fatura:
    fatura = Fatura.objects.select_for_update(of=("self",)).select_related("cartao__conta_pagamento_padrao").get(
        pk=fatura_id, usuario=usuario
    )
    if fatura.status == Fatura.Status.PAGA:
        return fatura
    try:
        validar_vencimento_no_ciclo(fatura.ciclo, vencimento)
    except VencimentoCartaoInvalido as exc:
        raise ValidationError(str(exc)) from exc
    parcelas, pendencias, bruto, creditos, proprio = _valores_confirmados(fatura)
    if pendencias:
        raise ValidationError("Confirme, transfira ou cancele todas as previsões antes do fechamento.")
    conta = conta or fatura.cartao.conta_pagamento_padrao
    if conta and conta.usuario_id != usuario.id:
        raise ValidationError("A conta de pagamento não pertence ao usuário.")

    transportes = list(
        SaldoTransportadoFatura.objects.select_for_update().filter(
            fatura_destino=fatura,
            status=SaldoTransportadoFatura.Status.CONFIRMADO,
        )
    )
    transportado = sum((item.valor for item in transportes), ZERO)
    total_exigido = proprio + transportado
    if total_exigido <= ZERO:
        raise ValidationError("A fatura não possui composição confirmada nem saldo transportado para fechar.")
    anteriores = list(fatura.fechamentos.select_for_update().order_by("-versao"))
    if anteriores and anteriores[0].status == FechamentoFatura.Status.ATIVO:
        anteriores[0].status = FechamentoFatura.Status.SUBSTITUIDO
        anteriores[0].save(update_fields=["status", "atualizado_em"])
    fechamento = FechamentoFatura.objects.create(
        fatura=fatura,
        versao=(anteriores[0].versao + 1) if anteriores else 1,
        total_bruto=bruto,
        total_creditos=creditos,
        total_proprio=proprio,
        total_transportado=transportado,
        total_exigido=total_exigido,
        vencimento=vencimento,
        conta_pagamento=conta,
        observacao=observacao,
    )
    ItemFechamentoFatura.objects.bulk_create(
        [
            ItemFechamentoFatura(
                fechamento=fechamento,
                parcela=parcela,
                descricao=parcela.descricao_exibicao,
                natureza=parcela.natureza_exibicao,
                valor=parcela.valor,
            )
            for parcela in parcelas
        ]
    )
    titulo, criado = Titulo.objects.select_for_update().get_or_create(
        fatura=fatura,
        defaults={
            "usuario": usuario,
            "tipo": Titulo.Tipo.PAGAR,
            "descricao": f"Fatura {fatura.cartao.nome} {fatura.ciclo}",
            "vencimento": vencimento,
            "valor_original": total_exigido,
            "saldo_aberto": total_exigido,
            "conta": conta,
        },
    )
    if not criado:
        ja_liquidado = titulo.liquidacoes.filter(status=Liquidacao.Status.ATIVA).aggregate(
            valor=Sum("valor", default=ZERO)
        )["valor"] or ZERO
        ja_transportado = titulo.transportes_saida.filter(
            status__in=[SaldoTransportadoFatura.Status.CONFIRMADO, SaldoTransportadoFatura.Status.INCORPORADO]
        ).aggregate(valor=Sum("valor", default=ZERO))["valor"] or ZERO
        if total_exigido < ja_liquidado + ja_transportado:
            raise ValidationError("O novo fechamento é menor que o valor já liquidado ou transportado.")
        titulo.descricao = f"Fatura {fatura.cartao.nome} {fatura.ciclo}"
        titulo.vencimento = vencimento
        titulo.valor_original = total_exigido
        titulo.conta = conta
        titulo.status = Titulo.Status.ABERTO
        titulo.ativo = True
        titulo.save(update_fields=["descricao", "vencimento", "valor_original", "conta", "status", "ativo", "atualizado_em"])
    for transporte in transportes:
        transporte.titulo_destino = titulo
        transporte.status = SaldoTransportadoFatura.Status.INCORPORADO
        transporte.save(update_fields=["titulo_destino", "status", "atualizado_em"])
    fatura.total_bruto = bruto
    fatura.total_creditos = creditos
    fatura.total = proprio
    fatura.total_transportado = transportado
    fatura.total_exigido = total_exigido
    fatura.fechamento = date.today()
    fatura.vencimento = vencimento
    fatura.status = Fatura.Status.FECHADA
    fatura.save(update_fields=["total_bruto", "total_creditos", "total", "total_transportado", "total_exigido", "fechamento", "vencimento", "status", "atualizado_em"])
    ParcelaCartao.objects.filter(fatura=fatura).update(vencimento=vencimento)
    _atualizar_titulo(titulo)
    _registrar(fatura, HistoricoFatura.Evento.FECHAMENTO, "Fatura fechada.", total_exigido, versao=fechamento.versao)
    return fatura


@transaction.atomic
def programar_pagamento(usuario, titulo_id: int, conta: Conta, data_programada: date, valor: Decimal, chave="", observacao=""):
    titulo = Titulo.objects.select_for_update(of=("self",)).select_related("fatura").get(
        pk=titulo_id, usuario=usuario, tipo=Titulo.Tipo.PAGAR
    )
    _validar_titulo_operavel(titulo)
    if chave:
        existente = ProgramacaoPagamento.objects.filter(titulo=titulo, chave_idempotencia=chave).first()
        if existente:
            return existente
    if conta.usuario_id != usuario.id or valor <= ZERO:
        raise ValidationError("Informe conta e valor válidos para a programação.")
    reservado = saldo_programado(titulo)
    if reservado + valor > titulo.saldo_aberto:
        raise ValidationError("As programações não podem superar o saldo exigível do título.")
    programacao = ProgramacaoPagamento.objects.create(
        titulo=titulo, conta=conta, data_programada=data_programada, valor_programado=valor,
        chave_idempotencia=chave, observacao=observacao,
    )
    if titulo.fatura_id:
        _registrar(titulo.fatura, HistoricoFatura.Evento.PROGRAMACAO, "Pagamento programado.", valor, programacao=programacao.pk)
    return programacao


def _aplicar_programacoes(liquidacao: Liquidacao, programacao_ids=None) -> None:
    titulo = liquidacao.titulo
    queryset = ProgramacaoPagamento.objects.select_for_update().filter(
        titulo=titulo, status__in=[ProgramacaoPagamento.Status.ATIVA, ProgramacaoPagamento.Status.PARCIAL]
    ).order_by("data_programada", "id")
    if programacao_ids:
        queryset = queryset.filter(pk__in=programacao_ids)
    restante = liquidacao.valor
    for programacao in queryset:
        disponivel = programacao.valor_programado - programacao.valor_realizado
        aplicado = min(disponivel, restante)
        if aplicado <= ZERO:
            continue
        AplicacaoLiquidacaoProgramacao.objects.create(
            liquidacao=liquidacao, programacao=programacao, valor=aplicado
        )
        programacao.valor_realizado += aplicado
        programacao.status = (
            ProgramacaoPagamento.Status.CONCLUIDA
            if programacao.valor_realizado >= programacao.valor_programado
            else ProgramacaoPagamento.Status.PARCIAL
        )
        programacao.save(update_fields=["valor_realizado", "status", "atualizado_em"])
        restante -= aplicado
        if restante <= ZERO:
            break


@transaction.atomic
def conciliar_pagamento(usuario, titulo_id: int, movimento_id: int, valor: Decimal | None = None, programacao_ids=None, origem=Liquidacao.Origem.CONCILIACAO, chave=""):
    titulo = Titulo.objects.select_for_update(of=("self",)).select_related("fatura").get(pk=titulo_id, usuario=usuario)
    if chave:
        existente = Liquidacao.objects.filter(titulo=titulo, chave_idempotencia=chave).first()
        if existente:
            return existente
    _validar_titulo_operavel(titulo)
    movimento = MovimentoConta.objects.select_for_update().select_related("conta").get(
        pk=movimento_id, conta__usuario=usuario
    )
    existente = Liquidacao.objects.filter(
        titulo=titulo, movimento_conta=movimento, status=Liquidacao.Status.ATIVA
    ).first()
    if existente:
        return existente
    valor = abs(valor if valor is not None else movimento.valor)
    ja_alocado = movimento.liquidacao_set.filter(status=Liquidacao.Status.ATIVA).aggregate(
        valor=Sum("valor", default=ZERO)
    )["valor"] or ZERO
    disponivel_movimento = abs(movimento.valor) - ja_alocado
    if valor <= ZERO or valor > disponivel_movimento or valor > titulo.saldo_aberto:
        raise ValidationError("O valor não está disponível para esta conciliação.")
    contas_programadas = set(titulo.programacoes.filter(
        status__in=[ProgramacaoPagamento.Status.ATIVA, ProgramacaoPagamento.Status.PARCIAL]
    ).values_list("conta_id", flat=True))
    if titulo.conta_id and movimento.conta_id != titulo.conta_id and movimento.conta_id not in contas_programadas:
        raise ValidationError("O movimento não pertence a uma conta prevista para este título.")
    liquidacao = Liquidacao.objects.create(
        titulo=titulo, movimento_conta=movimento, valor=valor, data=movimento.data_efetiva,
        origem=origem, chave_idempotencia=chave,
    )
    _aplicar_programacoes(liquidacao, programacao_ids)
    _atualizar_titulo(titulo)
    if titulo.fatura_id:
        _registrar(titulo.fatura, HistoricoFatura.Evento.LIQUIDACAO, "Pagamento conciliado.", valor, liquidacao=liquidacao.pk)
    return liquidacao


@transaction.atomic
def registrar_pagamento_manual(usuario, titulo_id: int, conta: Conta, data_pagamento: date, valor: Decimal, chave: str, observacao=""):
    titulo = Titulo.objects.select_for_update(of=("self",)).select_related("fatura").get(
        pk=titulo_id, usuario=usuario
    )
    _validar_titulo_operavel(titulo)
    if not chave:
        raise ValidationError("A chave idempotente é obrigatória para pagamento manual.")
    movimento = MovimentoConta.objects.filter(conta=conta, chave_idempotencia=chave).first()
    if not movimento:
        if conta.usuario_id != usuario.id:
            raise ValidationError("A conta não pertence ao usuário.")
        evento = EventoFinanceiro.objects.create(
            usuario=usuario, natureza=NaturezaEvento.PAGAMENTO_FATURA,
            descricao=f"Pagamento da fatura {titulo.fatura.ciclo if titulo.fatura_id else titulo.descricao}",
            data=data_pagamento, valor=valor, situacao=Situacao.REALIZADO, observacao=observacao,
        )
        movimento = MovimentoConta.objects.create(
            conta=conta, evento=evento, data_efetiva=data_pagamento, valor=-abs(valor),
            historico_original=evento.descricao, chave_idempotencia=chave,
        )
    liquidacao = conciliar_pagamento(
        usuario, titulo.pk, movimento.pk, valor=abs(valor),
        origem=Liquidacao.Origem.MANUAL, chave=chave,
    )
    reprocessar_saldo_conta(conta.pk, data_pagamento)
    return liquidacao


@transaction.atomic
def criar_transporte(usuario, titulo_origem_id: int, fatura_destino_id: int, valor: Decimal, data_identificacao: date, chave="", observacao=""):
    titulo = Titulo.objects.select_for_update(of=("self",)).select_related("fatura__cartao").get(pk=titulo_origem_id, usuario=usuario)
    _validar_titulo_operavel(titulo)
    destino = Fatura.objects.select_for_update().select_related("cartao").get(pk=fatura_destino_id, usuario=usuario)
    origem = titulo.fatura
    if not origem or origem.cartao_id != destino.cartao_id or origem.pk == destino.pk:
        raise ValidationError("O transporte deve ocorrer entre faturas diferentes do mesmo cartão.")
    if chave:
        existente = SaldoTransportadoFatura.objects.filter(titulo_origem=titulo, chave_idempotencia=chave).first()
        if existente:
            return existente
    if destino.status != Fatura.Status.ABERTA:
        raise ValidationError("A fatura de destino deve estar aberta para receber o transporte.")
    if valor <= ZERO or valor > titulo.saldo_aberto:
        raise ValidationError("O valor transportado não pode superar o saldo exigível.")
    if saldo_programado(titulo) > titulo.saldo_aberto - valor:
        raise ValidationError("Ajuste ou cancele programações da origem antes de transportar este saldo.")
    transporte = SaldoTransportadoFatura.objects.create(
        fatura_origem=origem, titulo_origem=titulo, fatura_destino=destino, valor=valor,
        data_identificacao=data_identificacao, status=SaldoTransportadoFatura.Status.CONFIRMADO,
        chave_idempotencia=chave, observacao=observacao,
    )
    _atualizar_titulo(titulo)
    _registrar(origem, HistoricoFatura.Evento.TRANSPORTE_SAIDA, "Saldo transportado para outra fatura.", valor, destino=destino.pk, transporte=transporte.pk)
    _registrar(destino, HistoricoFatura.Evento.TRANSPORTE_ENTRADA, "Saldo recebido de fatura anterior.", valor, origem=origem.pk, transporte=transporte.pk)
    return transporte


@transaction.atomic
def reabrir_fatura(usuario, fatura_id: int, motivo="") -> Fatura:
    fatura = Fatura.objects.select_for_update().get(pk=fatura_id, usuario=usuario)
    titulo = Titulo.objects.select_for_update().filter(fatura=fatura).first()
    if not titulo or fatura.status not in {Fatura.Status.FECHADA, Fatura.Status.PARCIAL, Fatura.Status.PAGA}:
        raise ValidationError("Somente uma fatura fechada pode ser reaberta ou corrigida.")
    if titulo and (titulo.liquidacoes.filter(status=Liquidacao.Status.ATIVA).exists() or titulo.transportes_saida.filter(status__in=[SaldoTransportadoFatura.Status.CONFIRMADO, SaldoTransportadoFatura.Status.INCORPORADO]).exists()):
        fatura.status = Fatura.Status.EM_CORRECAO
        _registrar(fatura, HistoricoFatura.Evento.CORRECAO, "Correção iniciada com pagamentos ou transportes preservados.", motivo=motivo)
    else:
        fatura.status = Fatura.Status.ABERTA
        if titulo:
            titulo.status = Titulo.Status.SUSPENSO
            titulo.ativo = False
            titulo.save(update_fields=["status", "ativo", "atualizado_em"])
        fechamento = fatura.fechamentos.filter(status=FechamentoFatura.Status.ATIVO).first()
        if fechamento:
            fechamento.status = FechamentoFatura.Status.REABERTO
            fechamento.save(update_fields=["status", "atualizado_em"])
        _registrar(fatura, HistoricoFatura.Evento.REABERTURA, "Fatura reaberta.", motivo=motivo)
    fatura.save(update_fields=["status", "atualizado_em"])
    return fatura
