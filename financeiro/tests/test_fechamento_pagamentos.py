from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from financeiro.models import (
    Ambito,
    Cartao,
    CompraCartao,
    Conta,
    EventoFinanceiro,
    Fatura,
    NaturezaEvento,
    ParcelaCartao,
    Situacao,
    Titulo,
)
from financeiro.services.fechamento_faturas import (
    fechar_fatura,
    programar_pagamento,
    registrar_pagamento_manual,
    criar_transporte,
)
from financeiro.services.dashboard import consultar_dashboard


class FechamentoPagamentoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="titular", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        self.cartao = Cartao.objects.create(
            usuario=self.usuario, nome="Cartão", conta_pagamento_padrao=self.conta, dia_vencimento=10
        )
        self.fatura = Fatura.objects.create(usuario=self.usuario, cartao=self.cartao, ciclo="2026-10")
        self._parcela(self.fatura, "100.00")

    def _parcela(self, fatura, valor):
        evento = EventoFinanceiro.objects.create(
            usuario=self.usuario, natureza=NaturezaEvento.DESPESA, descricao="Compra", data=date(2026, 10, 1),
            valor=Decimal(valor), ambito=Ambito.PESSOAL, situacao=Situacao.REALIZADO,
        )
        compra = CompraCartao.objects.create(
            usuario=self.usuario, cartao=self.cartao, evento=evento, estabelecimento="Compra",
            data_compra=date(2026, 10, 1), valor_total=Decimal(valor), total_parcelas=1,
        )
        return ParcelaCartao.objects.create(
            compra=compra, fatura=fatura, natureza=NaturezaEvento.DESPESA, descricao="Compra",
            data_original=date(2026, 10, 1), numero=1, total=1, valor=Decimal(valor), situacao=Situacao.REALIZADO,
        )

    def _fechar(self, fatura=None):
        return fechar_fatura(self.usuario, (fatura or self.fatura).pk, date(2026, 10, 20), self.conta)

    def test_fechamento_repetido_reutiliza_um_titulo_sem_movimento(self):
        self._fechar()
        self._fechar()
        titulo = Titulo.objects.get(fatura=self.fatura)
        self.assertEqual(Titulo.objects.filter(fatura=self.fatura).count(), 1)
        self.assertEqual(titulo.saldo_aberto, Decimal("100.00"))
        self.assertEqual(self.conta.movimentoconta_set.count(), 0)

    def test_fechamento_sincroniza_vencimento_e_rejeita_data_fora_do_ciclo(self):
        parcela = self.fatura.parcelas.get()
        self.assertEqual(parcela.vencimento, date(2026, 10, 10))

        with self.assertRaises(ValidationError):
            fechar_fatura(self.usuario, self.fatura.pk, date(2026, 11, 1), self.conta)

        self._fechar()
        parcela.refresh_from_db()
        self.fatura.refresh_from_db()
        self.assertEqual(self.fatura.vencimento, date(2026, 10, 20))
        self.assertEqual(parcela.vencimento, date(2026, 10, 20))

    def test_programacoes_multiplas_e_pagamento_parcial(self):
        self._fechar()
        titulo = Titulo.objects.get(fatura=self.fatura)
        primeira = programar_pagamento(self.usuario, titulo.pk, self.conta, date(2026, 10, 5), Decimal("40.00"), chave="p1")
        segunda = programar_pagamento(self.usuario, titulo.pk, self.conta, date(2026, 10, 10), Decimal("60.00"), chave="p2")
        with self.assertRaises(ValidationError):
            programar_pagamento(self.usuario, titulo.pk, self.conta, date(2026, 10, 12), Decimal("0.01"), chave="p3")
        registrar_pagamento_manual(self.usuario, titulo.pk, self.conta, date(2026, 10, 5), Decimal("30.00"), "manual-1")
        titulo.refresh_from_db()
        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(titulo.saldo_aberto, Decimal("70.00"))
        self.assertEqual(primeira.valor_realizado, Decimal("30.00"))
        self.assertEqual(primeira.status, "PARCIAL")
        self.assertEqual(segunda.valor_realizado, Decimal("0.00"))

    def test_dashboard_nao_duplica_titulo_e_programacoes(self):
        self._fechar()
        titulo = Titulo.objects.get(fatura=self.fatura)
        programar_pagamento(self.usuario, titulo.pk, self.conta, date(2026, 10, 5), Decimal("40.00"), chave="p1")
        consulta = consultar_dashboard(self.usuario, periodo="2026-10")
        self.assertEqual(consulta["total_debitos_previstos"], Decimal("100.00"))

    def test_transporte_reduz_origem_e_evita_nova_despesa(self):
        self._fechar()
        titulo = Titulo.objects.get(fatura=self.fatura)
        destino = Fatura.objects.create(usuario=self.usuario, cartao=self.cartao, ciclo="2026-11")
        transporte = criar_transporte(
            self.usuario, titulo.pk, destino.pk, Decimal("100.00"), date(2026, 11, 1), chave="transporte-1"
        )
        titulo.refresh_from_db()
        self.assertEqual(titulo.saldo_aberto, Decimal("0.00"))
        self.assertEqual(transporte.status, "CONFIRMADO")
        self.assertEqual(EventoFinanceiro.objects.filter(natureza=NaturezaEvento.DESPESA).count(), 1)

    def test_fatura_destino_fecha_somente_com_saldo_transportado(self):
        self._fechar()
        origem = Titulo.objects.get(fatura=self.fatura)
        destino = Fatura.objects.create(usuario=self.usuario, cartao=self.cartao, ciclo="2026-11")
        criar_transporte(self.usuario, origem.pk, destino.pk, Decimal("100.00"), date(2026, 11, 1), chave="transporte-2")
        fechar_fatura(self.usuario, destino.pk, date(2026, 11, 20), self.conta)
        titulo_destino = Titulo.objects.get(fatura=destino)
        destino.refresh_from_db()
        self.assertEqual(titulo_destino.valor_original, Decimal("100.00"))
        self.assertEqual(destino.total_transportado, Decimal("100.00"))
