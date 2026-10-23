from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import (
    Ambito,
    Cartao,
    Categoria,
    CompraCartao,
    Conta,
    EventoFinanceiro,
    Fatura,
    MovimentoConta,
    NaturezaEvento,
    Orcamento,
    ParcelaCartao,
    RateioCategoria,
    Situacao,
)
from financeiro.services.orcamentos import (
    IMPORTACAO_COMPLETA,
    IMPORTACAO_PARCIAL,
    ImportacaoDespesasOrcamentoInvalida,
    _faixa_percentual,
    _percentual_realizado,
    alertas_orcamento_dashboard,
    consolidar_despesas_para_orcamento,
    enriquecer_orcamentos_com_realizado,
    importar_despesas_para_orcamento,
    previsualizar_importacao_despesas,
    resumir_orcamento_dashboard,
)
from financeiro.services.detalhamento_dashboard import consultar_detalhamento_dashboard
from financeiro.services.lancamentos import consultar_lancamentos


class RealizacaoOrcamentosTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="realizado-orcamento", password="senha")
        self.outro_usuario = get_user_model().objects.create_user(username="realizado-outro", password="senha")
        self.categoria = Categoria.objects.create(usuario=self.usuario, nome="Alimentação")
        self.filha = Categoria.objects.create(
            usuario=self.usuario,
            nome="Restaurantes",
            categoria_pai=self.categoria,
        )
        self.neta = Categoria.objects.create(
            usuario=self.usuario,
            nome="Delivery",
            categoria_pai=self.filha,
        )
        self.nao_computavel = Categoria.objects.create(
            usuario=self.usuario,
            nome="Despesa não computável",
            categoria_pai=self.categoria,
            computa_resultado=False,
        )
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        self.cartao = Cartao.objects.create(usuario=self.usuario, nome="Cartão principal", dia_vencimento=10)
        self.fatura = Fatura.objects.create(
            usuario=self.usuario,
            cartao=self.cartao,
            ciclo="2026-10",
            vencimento=date(2026, 10, 10),
        )
        self.orcamento = Orcamento.objects.create(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="500.00",
        )

    def movimento(
        self,
        valor,
        *,
        categoria=None,
        natureza=NaturezaEvento.DESPESA,
        ambito=Ambito.PESSOAL,
        situacao=Situacao.REALIZADO,
        data_evento=date(2026, 10, 5),
        usuario=None,
        conta=None,
    ):
        usuario = usuario or self.usuario
        evento = EventoFinanceiro.objects.create(
            usuario=usuario,
            natureza=natureza,
            descricao=f"Movimento {valor}",
            data=data_evento,
            valor=valor,
            ambito=ambito,
            situacao=situacao,
        )
        if categoria:
            RateioCategoria.objects.create(evento=evento, categoria=categoria, valor=valor)
        MovimentoConta.objects.create(
            conta=conta or self.conta,
            evento=evento,
            data_efetiva=data_evento,
            valor=-abs(Decimal(valor)),
        )
        return evento

    def parcela(
        self,
        valor,
        *,
        categoria=None,
        natureza=NaturezaEvento.DESPESA,
        ambito="",
        ambito_evento=Ambito.PESSOAL,
        situacao=Situacao.PREVISTO,
    ):
        evento = EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=natureza,
            descricao=f"Compra {valor}",
            data=date(2026, 9, 20),
            valor=valor,
            ambito=ambito_evento,
            situacao=Situacao.REALIZADO,
        )
        compra = CompraCartao.objects.create(
            usuario=self.usuario,
            cartao=self.cartao,
            evento=evento,
            estabelecimento="Estabelecimento",
            data_compra=date(2026, 9, 20),
            valor_total=valor,
        )
        return ParcelaCartao.objects.create(
            compra=compra,
            fatura=self.fatura,
            natureza=natureza,
            vencimento=date(2026, 10, 10),
            categoria=categoria,
            ambito=ambito,
            valor=valor,
            situacao=situacao,
        )

    def test_soma_conta_cartao_descendentes_e_estorno_pelas_regras_do_dashboard(self):
        self.movimento("100.00", categoria=self.filha)
        self.parcela("150.00", categoria=self.neta, situacao=Situacao.PREVISTO)
        self.movimento("20.00", categoria=self.neta, natureza=NaturezaEvento.ESTORNO)
        self.movimento("80.00", categoria=self.nao_computavel)
        self.movimento("60.00", categoria=self.filha, natureza=NaturezaEvento.PAGAMENTO_FATURA)
        self.movimento("70.00", categoria=self.filha, natureza=NaturezaEvento.TRANSFERENCIA)

        [orcamento] = enriquecer_orcamentos_com_realizado(self.usuario, [self.orcamento])

        self.assertEqual(orcamento.realizado, Decimal("230.00"))
        self.assertEqual(orcamento.percentual_realizado, Decimal("46.00"))
        self.assertEqual(orcamento.percentual_css, "46.00")
        self.assertEqual(orcamento.faixa_percentual, "blue")

    def test_importacao_consolida_base_do_realizado_e_contabiliza_ignorados(self):
        self.movimento("100.00", categoria=self.filha)
        self.parcela("30.00", categoria=self.neta)
        self.movimento("20.00", categoria=self.neta, natureza=NaturezaEvento.ESTORNO)
        self.movimento("50.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)
        self.movimento("80.00", categoria=self.nao_computavel)
        self.movimento("60.00", categoria=self.filha, natureza=NaturezaEvento.PAGAMENTO_FATURA)
        self.movimento("70.00", categoria=self.filha, natureza=NaturezaEvento.TRANSFERENCIA)
        self.movimento("25.00")

        categoria_inativa = Categoria.objects.create(
            usuario=self.usuario,
            nome="Categoria inativa",
            ativa=False,
        )
        filha_inativa = Categoria.objects.create(
            usuario=self.usuario,
            nome="Filha inativa",
            categoria_pai=categoria_inativa,
        )
        self.movimento("40.00", categoria=filha_inativa)

        categoria_zerada = Categoria.objects.create(usuario=self.usuario, nome="Categoria zerada")
        filha_zerada = Categoria.objects.create(
            usuario=self.usuario,
            nome="Filha zerada",
            categoria_pai=categoria_zerada,
        )
        self.movimento("35.00", categoria=filha_zerada)
        self.movimento("35.00", categoria=filha_zerada, natureza=NaturezaEvento.ESTORNO)

        conta_outro = Conta.objects.create(usuario=self.outro_usuario, nome="Conta externa")
        categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria externa")
        self.movimento(
            "900.00",
            categoria=categoria_outro,
            usuario=self.outro_usuario,
            conta=conta_outro,
        )

        resumo = consolidar_despesas_para_orcamento(self.usuario, "2026-10")

        self.assertEqual(
            {(item["categoria_id"], item["ambito"], item["valor"]) for item in resumo["itens"]},
            {
                (self.categoria.pk, Ambito.PESSOAL, Decimal("110.00")),
                (self.categoria.pk, Ambito.PROFISSIONAL, Decimal("50.00")),
            },
        )
        self.assertEqual(resumo["quantidade_importavel"], 2)
        self.assertEqual(resumo["valor_importavel"], Decimal("160.00"))
        self.assertEqual(resumo["quantidade_ignorados"], 3)
        self.assertEqual(resumo["ignorados"]["sem_categoria"]["quantidade"], 1)
        self.assertEqual(resumo["ignorados"]["categoria_inativa"]["quantidade"], 1)
        self.assertEqual(resumo["ignorados"]["nao_positivos"]["quantidade"], 1)

    def test_previa_e_importacao_completa_substituem_somente_destino_do_usuario(self):
        self.movimento("100.00", categoria=self.filha)
        self.movimento("50.00", categoria=self.neta, ambito=Ambito.PROFISSIONAL)
        antigo = Orcamento.objects.create(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
            limite="999.00",
        )
        categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria externa")
        alheio = Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=categoria_outro,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
            limite="888.00",
        )

        previa = previsualizar_importacao_despesas(self.usuario, "2026-10", "2026-11")
        resultado = importar_despesas_para_orcamento(
            self.usuario,
            "2026-10",
            "2026-11",
            IMPORTACAO_COMPLETA,
        )

        self.assertEqual(previa["quantidade_destino"], 1)
        self.assertEqual(previa["quantidade_faltantes"], 1)
        self.assertEqual(resultado["incluidos"], 2)
        self.assertEqual(resultado["substituidos"], 1)
        self.assertFalse(Orcamento.objects.filter(pk=antigo.pk).exists())
        self.assertTrue(Orcamento.objects.filter(pk=alheio.pk).exists())
        self.assertEqual(
            set(
                Orcamento.objects.filter(usuario=self.usuario, mes="2026-11").values_list(
                    "categoria_id", "ambito", "limite"
                )
            ),
            {
                (self.categoria.pk, Ambito.PESSOAL, Decimal("100.00")),
                (self.categoria.pk, Ambito.PROFISSIONAL, Decimal("50.00")),
            },
        )

    def test_importacao_parcial_preserva_existentes_e_usa_categoria_mais_ambito(self):
        self.movimento("100.00", categoria=self.filha)
        self.movimento("50.00", categoria=self.neta, ambito=Ambito.PROFISSIONAL)
        existente = Orcamento.objects.create(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
            limite="999.00",
        )

        resultado = importar_despesas_para_orcamento(
            self.usuario,
            "2026-10",
            "2026-11",
            IMPORTACAO_PARCIAL,
        )

        existente.refresh_from_db()
        self.assertEqual(existente.limite, Decimal("999.00"))
        self.assertEqual(resultado["incluidos"], 1)
        self.assertEqual(resultado["preservados"], 1)
        self.assertTrue(
            Orcamento.objects.filter(
                usuario=self.usuario,
                categoria=self.categoria,
                mes="2026-11",
                ambito=Ambito.PROFISSIONAL,
                limite="50.00",
            ).exists()
        )

    def test_confirmacao_da_importacao_recalcula_as_despesas(self):
        self.movimento("100.00", categoria=self.filha)
        previa = previsualizar_importacao_despesas(self.usuario, "2026-10", "2026-11")
        self.assertEqual(previa["valor_importavel"], Decimal("100.00"))
        self.movimento("25.00", categoria=self.neta)

        importar_despesas_para_orcamento(
            self.usuario,
            "2026-10",
            "2026-11",
            IMPORTACAO_COMPLETA,
        )

        criado = Orcamento.objects.get(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
        )
        self.assertEqual(criado.limite, Decimal("125.00"))

    @patch("financeiro.services.orcamentos.timezone.localdate", return_value=date(2026, 10, 22))
    def test_importacao_rejeita_origem_futura_destino_nao_posterior_e_sem_despesas(self, _localdate):
        with self.assertRaisesMessage(
            ImportacaoDespesasOrcamentoInvalida,
            "não pode ser posterior ao mês atual",
        ):
            importar_despesas_para_orcamento(
                self.usuario,
                "2026-11",
                "2026-12",
                IMPORTACAO_COMPLETA,
            )
        with self.assertRaisesMessage(
            ImportacaoDespesasOrcamentoInvalida,
            "deve ser posterior",
        ):
            importar_despesas_para_orcamento(
                self.usuario,
                "2026-10",
                "2026-10",
                IMPORTACAO_COMPLETA,
            )
        with self.assertRaisesMessage(
            ImportacaoDespesasOrcamentoInvalida,
            "Nenhuma despesa elegível",
        ):
            importar_despesas_para_orcamento(
                self.usuario,
                "2026-09",
                "2026-10",
                IMPORTACAO_COMPLETA,
            )

    def test_importacao_completa_faz_rollback_se_a_criacao_falhar(self):
        self.movimento("100.00", categoria=self.filha)
        destino = Orcamento.objects.create(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
            limite="999.00",
        )

        with patch(
            "financeiro.services.orcamentos.Orcamento.objects.bulk_create",
            side_effect=IntegrityError("conflito simulado"),
        ):
            with self.assertRaises(IntegrityError):
                importar_despesas_para_orcamento(
                    self.usuario,
                    "2026-10",
                    "2026-11",
                    IMPORTACAO_COMPLETA,
                )

        destino.refresh_from_db()
        self.assertEqual(destino.limite, Decimal("999.00"))

    def test_exclui_conta_nao_realizada_outro_ambito_periodo_e_usuario(self):
        self.movimento("40.00", categoria=self.filha)
        self.movimento("100.00", categoria=self.filha, situacao=Situacao.PREVISTO)
        self.movimento("110.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)
        self.movimento("120.00", categoria=self.filha, data_evento=date(2026, 9, 30))
        conta_outro = Conta.objects.create(usuario=self.outro_usuario, nome="Conta externa")
        categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria externa")
        self.movimento(
            "130.00",
            categoria=categoria_outro,
            usuario=self.outro_usuario,
            conta=conta_outro,
        )

        [orcamento] = enriquecer_orcamentos_com_realizado(self.usuario, [self.orcamento])

        self.assertEqual(orcamento.realizado, Decimal("40.00"))

    def test_cartao_usa_ambito_da_parcela_e_fallback_do_evento(self):
        self.parcela("30.00", categoria=self.filha, ambito="", ambito_evento=Ambito.PESSOAL)
        self.parcela("70.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)

        [orcamento] = enriquecer_orcamentos_com_realizado(self.usuario, [self.orcamento])

        self.assertEqual(orcamento.realizado, Decimal("30.00"))

    def test_sem_movimento_e_limite_zero_sao_tratados_sem_divisao(self):
        self.orcamento.limite = Decimal("0.00")

        [orcamento] = enriquecer_orcamentos_com_realizado(self.usuario, [self.orcamento])

        zero = Decimal("0.00")
        self.assertEqual(orcamento.realizado, zero)
        self.assertIsNone(orcamento.percentual_realizado)
        self.assertEqual(orcamento.percentual_css, "0.00")
        self.assertEqual(orcamento.faixa_percentual, "neutral")
        self.assertEqual(_percentual_realizado(Decimal("-10.00"), Decimal("100.00")), zero)

    def test_faixas_percentuais_e_limite_visual(self):
        casos = (
            (Decimal("0.00"), "blue"),
            (Decimal("80.00"), "blue"),
            (Decimal("80.01"), "orange"),
            (Decimal("90.00"), "orange"),
            (Decimal("90.01"), "red"),
            (Decimal("125.00"), "red"),
        )
        for percentual, faixa in casos:
            with self.subTest(percentual=percentual):
                self.assertEqual(_faixa_percentual(percentual), faixa)

        self.movimento("625.00", categoria=self.filha)
        [orcamento] = enriquecer_orcamentos_com_realizado(self.usuario, [self.orcamento])
        self.assertEqual(orcamento.percentual_realizado, Decimal("125.00"))
        self.assertEqual(orcamento.percentual_css, "100.00")

    def test_resumo_dashboard_consolida_ambitos_ordena_e_isola_usuario(self):
        Orcamento.objects.create(
            usuario=self.usuario,
            categoria=self.categoria,
            mes="2026-10",
            ambito=Ambito.PROFISSIONAL,
            limite="300.00",
        )
        transporte = Categoria.objects.create(usuario=self.usuario, nome="Transporte")
        Orcamento.objects.create(
            usuario=self.usuario,
            categoria=transporte,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="200.00",
        )
        categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria alheia")
        Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=categoria_outro,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="900.00",
        )
        self.movimento("460.00", categoria=self.filha, ambito=Ambito.PESSOAL)
        self.movimento(
            "10.00",
            categoria=self.filha,
            ambito=Ambito.PESSOAL,
            natureza=NaturezaEvento.ESTORNO,
        )
        self.movimento("350.00", categoria=self.neta, ambito=Ambito.PROFISSIONAL)
        self.movimento("100.00", categoria=transporte, ambito=Ambito.PESSOAL)

        resumo = resumir_orcamento_dashboard(self.usuario, "2026-10")

        self.assertEqual(resumo["total_orcado"], Decimal("1000.00"))
        self.assertEqual(resumo["mes_rotulo"], "10/2026")
        self.assertEqual([item["nome"] for item in resumo["categorias"]], ["Alimentação", "Transporte"])
        alimentacao = resumo["categorias"][0]
        self.assertEqual(alimentacao["orcado"], Decimal("800.00"))
        self.assertEqual(alimentacao["realizado"], Decimal("800.00"))
        self.assertEqual(alimentacao["participacao"], Decimal("80.00"))
        self.assertEqual(alimentacao["percentual_comprometido"], Decimal("100.00"))
        self.assertEqual(alimentacao["percentual_comprometido_css"], "100.00")
        self.assertNotIn("scope", parse_qs(urlparse(alimentacao["detalhe_url"]).query))
        self.assertNotIn("analysis_scope", parse_qs(urlparse(alimentacao["lancamentos_url"]).query))

    def test_resumo_dashboard_deixa_percentual_invalido_por_ultimo(self):
        self.orcamento.limite = Decimal("0.00")
        self.orcamento.save(update_fields=["limite"])
        transporte = Categoria.objects.create(usuario=self.usuario, nome="Transporte")
        Orcamento.objects.create(
            usuario=self.usuario,
            categoria=transporte,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="100.00",
        )
        self.movimento("125.00", categoria=transporte)

        resumo = resumir_orcamento_dashboard(self.usuario, "2026-10")

        self.assertEqual([item["nome"] for item in resumo["categorias"]], ["Transporte", "Alimentação"])
        self.assertEqual(resumo["categorias"][0]["percentual_comprometido"], Decimal("125.00"))
        self.assertEqual(resumo["categorias"][0]["percentual_comprometido_css"], "100.00")
        self.assertIsNone(resumo["categorias"][1]["percentual_comprometido"])
        self.assertEqual(resumo["categorias"][1]["faixa_percentual"], "neutral")

    def test_alertas_dashboard_respeitam_limites_e_prioridade(self):
        def categoria(nome, percentual):
            return {
                "nome": nome,
                "percentual_comprometido": Decimal(percentual),
                "realizado": Decimal("100.00"),
                "orcado": Decimal("100.00"),
            }

        alertas = alertas_orcamento_dashboard(
            {
                "categorias": [
                    categoria("Estourado", "100.01"),
                    categoria("Atingido", "100.00"),
                    categoria("Próximo", "90.00"),
                    categoria("Seguro", "89.99"),
                ]
            }
        )

        self.assertEqual([item["titulo"] for item in alertas], ["Estourado", "Atingido", "Próximo"])
        self.assertIn("Orçamento estourado", alertas[0]["mensagem"])
        self.assertIn("Limite do orçamento atingido", alertas[1]["mensagem"])
        self.assertIn("Orçamento próximo do limite", alertas[2]["mensagem"])

    def test_lista_renderiza_colunas_valor_barra_e_texto_acessivel(self):
        self.movimento("450.00", categoria=self.filha)
        self.client.force_login(self.usuario)

        resposta = self.client.get(reverse("orcamentos"), {"mes": "10/2026"})

        self.assertContains(resposta, "Realizado")
        self.assertContains(resposta, "% realizado")
        self.assertContains(resposta, "R$ 450,00")
        self.assertContains(resposta, "90,00%")
        self.assertContains(resposta, "budget-progress-orange")
        self.assertContains(resposta, 'style="width:90.00%"')
        self.assertContains(resposta, 'role="img"')
        self.assertContains(resposta, "data-budget-detail-url")

        orcamento = resposta.context["orcamentos"][0]
        detalhe = parse_qs(urlparse(orcamento.detalhe_url).query)
        self.assertEqual(detalhe["date_from"], ["01/10/2026"])
        self.assertEqual(detalhe["date_to"], ["31/10/2026"])
        self.assertEqual(detalhe["type"], ["category"])
        self.assertEqual(detalhe["value"], [str(self.categoria.pk)])
        self.assertEqual(detalhe["scope"], [Ambito.PESSOAL])

        fallback = parse_qs(urlparse(orcamento.lancamentos_url).query)
        self.assertEqual(fallback["analysis_scope"], [Ambito.PESSOAL])
        self.assertEqual(fallback["parent_category"], [str(self.categoria.pk)])
        self.assertEqual(fallback["computes"], ["COMPUTA"])

    def test_detalhamento_filtra_ambito_efetivo_de_conta_e_cartao(self):
        self.movimento("40.00", categoria=self.filha, ambito=Ambito.PESSOAL)
        self.movimento("60.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)
        self.parcela("20.00", categoria=self.neta, ambito="", ambito_evento=Ambito.PESSOAL)
        self.parcela("30.00", categoria=self.neta, ambito=Ambito.PROFISSIONAL)

        pessoal = consultar_detalhamento_dashboard(
            self.usuario,
            tipo="category",
            valor=str(self.categoria.pk),
            scope=Ambito.PESSOAL,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
        )
        todos = consultar_detalhamento_dashboard(
            self.usuario,
            tipo="category",
            valor=str(self.categoria.pk),
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
        )

        self.assertEqual(pessoal["total_indicador"], Decimal("60.00"))
        self.assertEqual({linha.descricao for linha in pessoal["linhas"]}, {"Movimento 40.00", "Compra 20.00"})
        self.assertEqual(todos["total_indicador"], Decimal("150.00"))
        self.assertNotIn("analysis_scope", parse_qs(urlparse(todos["lancamentos_url"]).query))

    def test_fallback_de_lancamentos_preserva_e_aplica_ambito_analitico(self):
        self.movimento("35.00", categoria=self.filha, ambito=Ambito.PESSOAL)
        self.movimento("75.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)

        contexto = consultar_lancamentos(
            self.usuario,
            data_inicial="01/10/2026",
            data_final="31/10/2026",
            categoria_superior=str(self.categoria.pk),
            computa_resultado="COMPUTA",
            analysis_type="category",
            analysis_value=str(self.categoria.pk),
            analysis_scope=Ambito.PESSOAL,
        )

        self.assertEqual(contexto["total_indicador"], Decimal("35.00"))
        self.assertEqual([linha.descricao for linha in contexto["linhas"]], ["Movimento 35.00"])
        self.assertEqual(contexto["analysis_scope"], Ambito.PESSOAL)
        self.assertIn("analysis_scope=PESSOAL", contexto["filtros_query"])

    def test_icone_fica_desabilitado_no_zero_e_ativo_no_realizado_negativo(self):
        self.client.force_login(self.usuario)
        resposta_zero = self.client.get(reverse("orcamentos"), {"mes": "10/2026"})
        self.assertContains(resposta_zero, 'aria-disabled="true"')
        self.assertContains(resposta_zero, "Sem lançamentos realizados para detalhar")

        self.movimento("10.00", categoria=self.filha, natureza=NaturezaEvento.ESTORNO)
        resposta_negativo = self.client.get(reverse("orcamentos"), {"mes": "10/2026"})
        self.assertEqual(resposta_negativo.context["orcamentos"][0].realizado, Decimal("-10.00"))
        self.assertContains(resposta_negativo, "data-budget-detail-url")
        self.assertNotContains(resposta_negativo, 'aria-disabled="true"')

    def test_endpoint_ajax_recebe_scope_sem_alterar_chamada_sem_scope(self):
        self.movimento("25.00", categoria=self.filha, ambito=Ambito.PESSOAL)
        self.movimento("55.00", categoria=self.filha, ambito=Ambito.PROFISSIONAL)
        self.client.force_login(self.usuario)
        parametros = {
            "type": "category",
            "value": self.categoria.pk,
            "date_from": "01/10/2026",
            "date_to": "31/10/2026",
        }

        resposta_pessoal = self.client.get(
            reverse("dashboard_detalhamento"),
            {**parametros, "scope": Ambito.PESSOAL},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        resposta_todos = self.client.get(
            reverse("dashboard_detalhamento"),
            parametros,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertContains(resposta_pessoal, "Movimento 25.00")
        self.assertNotContains(resposta_pessoal, "Movimento 55.00")
        self.assertContains(resposta_todos, "Movimento 25.00")
        self.assertContains(resposta_todos, "Movimento 55.00")
