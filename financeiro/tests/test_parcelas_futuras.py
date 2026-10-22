from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from financeiro.models import (
    Ambito,
    Categoria,
    Cartao,
    CompraCartao,
    Conta,
    EventoFinanceiro,
    Fatura,
    NaturezaEvento,
    ParcelaCartao,
    Pessoa,
    Situacao,
)
from financeiro.services.cartoes_faturas import criar_compra_cartao
from financeiro.services.parcelas_futuras import consultar_parcelas_futuras


class ParcelasFuturasServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.usuario = user_model.objects.create_user(username="titular", password="senha")
        self.outro_usuario = user_model.objects.create_user(username="outro", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        self.conta_inativa = Conta.objects.create(usuario=self.usuario, nome="Conta histórica", ativa=False)
        self.cartao = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão principal",
            conta_pagamento_padrao=self.conta,
            dia_vencimento=10,
        )
        self.cartao_inativo = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão histórico",
            conta_pagamento_padrao=self.conta_inativa,
            dia_vencimento=10,
            ativo=False,
        )
        self.cartao_alheio = Cartao.objects.create(
            usuario=self.outro_usuario, nome="Cartão alheio", dia_vencimento=10
        )

    def _dados_compra(self, **alteracoes):
        dados = {
            "descricao": "Compra parcelada",
            "natureza": NaturezaEvento.DESPESA,
            "data_original": date(2026, 10, 5),
            "valor": Decimal("100.00"),
            "cartao": self.cartao,
            "categoria": None,
            "pessoa": None,
            "ambito": Ambito.PESSOAL,
            "situacao": Situacao.REALIZADO,
            "vencimento": None,
            "ciclo": "2026-10",
            "quantidade_parcelas": 3,
        }
        dados.update(alteracoes)
        return dados

    def _compra_historica(self, descricao="Compra importada", total=6):
        evento = EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=NaturezaEvento.DESPESA,
            descricao=descricao,
            data=date(2026, 8, 5),
            valor=Decimal("600.00"),
        )
        return CompraCartao.objects.create(
            usuario=self.usuario,
            cartao=self.cartao,
            evento=evento,
            estabelecimento=descricao,
            data_compra=date(2026, 8, 5),
            valor_total=Decimal("600.00"),
            valor_total_estimado=True,
            total_parcelas=total,
        )

    def _parcela(self, compra, ciclo, numero, total, valor, **alteracoes):
        fatura, _ = Fatura.objects.get_or_create(
            usuario=compra.usuario,
            cartao=compra.cartao,
            ciclo=ciclo,
        )
        dados = {
            "compra": compra,
            "fatura": fatura,
            "natureza": NaturezaEvento.DESPESA,
            "descricao": compra.estabelecimento,
            "data_original": compra.data_compra,
            "numero": numero,
            "total": total,
            "valor": Decimal(valor),
            "situacao": Situacao.PREVISTO if ciclo > "2026-10" else Situacao.REALIZADO,
        }
        dados.update(alteracoes)
        return ParcelaCartao.objects.create(**dados)

    def test_preserva_centavos_e_recalcula_a_ultima_parcela_pelo_periodo(self):
        criar_compra_cartao(self.usuario, self._dados_compra())

        outubro = consultar_parcelas_futuras(self.usuario, ciclo="2026-10", cartao_id=self.cartao.pk)
        novembro = consultar_parcelas_futuras(self.usuario, ciclo="2026-11", cartao_id=self.cartao.pk)

        self.assertEqual(
            [(item["ciclo"], item["total"]) for item in outubro["projecoes"]],
            [("2026-11", Decimal("33.33")), ("2026-12", Decimal("33.33"))],
        )
        self.assertEqual([item["origem"] for item in outubro["contribuicoes"]], ["explicito", "explicito"])
        self.assertEqual((outubro["compras"][0]["numero"], outubro["compras"][0]["valor"]), (1, Decimal("33.34")))
        self.assertEqual(outubro["quantidade_compras"], 1)
        self.assertEqual(outubro["total_compras"], Decimal("33.34"))
        self.assertEqual([(item["ciclo"], item["total"]) for item in novembro["projecoes"]], [("2026-12", Decimal("33.33"))])
        self.assertEqual(novembro["compras"][0]["numero"], 2)

    def test_estimativa_vira_o_ano_e_parcela_explicita_substitui_o_valor(self):
        compra = self._compra_historica()
        self._parcela(compra, "2026-10", 3, 6, "100.00", situacao=Situacao.REALIZADO)
        self._parcela(compra, "2026-12", 5, 6, "99.99")
        self._parcela(compra, "2027-01", 6, 6, "100.00")

        consulta = consultar_parcelas_futuras(self.usuario, ciclo="2026-10")

        self.assertEqual(
            [(item["ciclo"], item["total"]) for item in consulta["projecoes"]],
            [
                ("2026-11", Decimal("100.00")),
                ("2026-12", Decimal("99.99")),
                ("2027-01", Decimal("100.00")),
            ],
        )
        self.assertEqual(
            [item["origem"] for item in consulta["contribuicoes"]],
            ["estimado", "estimado", "estimado"],
        )

    def test_compra_futura_sem_historico_entra_uma_vez_no_calendario_e_nao_na_tabela(self):
        compra = self._compra_historica(descricao="Compra ainda não iniciada", total=3)
        self._parcela(compra, "2027-01", 1, 3, "45.00")

        consulta = consultar_parcelas_futuras(self.usuario, ciclo="2026-10")

        self.assertEqual([(item["ciclo"], item["total"]) for item in consulta["projecoes"]], [("2027-01", Decimal("45.00"))])
        self.assertEqual(consulta["compras"], [])
        self.assertEqual(len(consulta["contribuicoes"]), 1)

    def test_compras_concluidas_e_distintas_permanecem_separadas(self):
        criar_compra_cartao(
            self.usuario,
            self._dados_compra(descricao="Mesmo estabelecimento", valor=Decimal("40.00"), quantidade_parcelas=2),
        )
        criar_compra_cartao(
            self.usuario,
            self._dados_compra(descricao="Mesmo estabelecimento", valor=Decimal("60.00"), quantidade_parcelas=2),
        )

        consulta = consultar_parcelas_futuras(self.usuario, ciclo="2026-11")

        self.assertEqual(len(consulta["compras"]), 2)
        self.assertEqual([item["numero"] for item in consulta["compras"]], [2, 2])
        self.assertEqual(consulta["projecoes"], [])

    def test_compras_mostra_somente_parcelas_do_ciclo_selecionado(self):
        compra_dezembro = self._compra_historica(descricao="Compra encerrada em dezembro", total=6)
        self._parcela(compra_dezembro, "2026-12", 6, 6, "100.00")
        compra_janeiro = self._compra_historica(descricao="Compra com parcela em janeiro", total=3)
        self._parcela(compra_janeiro, "2027-01", 1, 3, "45.00")

        consulta = consultar_parcelas_futuras(self.usuario, ciclo="2027-01")

        self.assertEqual(
            [item["descricao"] for item in consulta["compras"]],
            ["Compra com parcela em janeiro"],
        )
        self.assertEqual(consulta["compras"][0]["ultimo_ciclo"], "2027-01")
        self.assertEqual(consulta["quantidade_compras"], 1)
        self.assertEqual(consulta["total_compras"], Decimal("45.00"))

    @patch("financeiro.services.parcelas_futuras.timezone.localdate", return_value=date(2026, 10, 21))
    def test_consulta_sem_ciclo_seleciona_o_mes_corrente(self, _localdate):
        Fatura.objects.create(usuario=self.usuario, cartao=self.cartao, ciclo="2027-08")

        consulta = consultar_parcelas_futuras(self.usuario)

        self.assertEqual(consulta["ciclo_selecionado"], "2026-10")
        self.assertEqual(
            [ciclo["valor"] for ciclo in consulta["ciclos"]],
            ["2027-08", "2026-10"],
        )

    def test_anuidade_filtros_e_isolamento_por_usuario(self):
        criar_compra_cartao(self.usuario, self._dados_compra(descricao="ANUIDADE DO CARTAO"))
        self.cartao_inativo.ativo = True
        self.cartao_inativo.save(update_fields=["ativo"])
        criar_compra_cartao(
            self.usuario,
            self._dados_compra(descricao="Compra do cartão inativo", cartao=self.cartao_inativo),
        )
        self.cartao_inativo.ativo = False
        self.cartao_inativo.save(update_fields=["ativo"])
        conta_alheia = Conta.objects.create(usuario=self.outro_usuario, nome="Conta alheia")
        self.cartao_alheio.conta_pagamento_padrao = conta_alheia
        self.cartao_alheio.save(update_fields=["conta_pagamento_padrao"])
        criar_compra_cartao(
            self.outro_usuario,
            self._dados_compra(cartao=self.cartao_alheio, descricao="Compra alheia"),
        )

        consulta = consultar_parcelas_futuras(
            self.usuario,
            ciclo="2026-10",
            conta_id=self.conta_inativa.pk,
            cartao_id=self.cartao_alheio.pk,
        )

        self.assertIsNone(consulta["cartao_selecionado"])
        self.assertEqual([cartao.pk for cartao in consulta["cartoes_compativeis"]], [self.cartao_inativo.pk])
        self.assertEqual([item["descricao"] for item in consulta["compras"]], ["Compra do cartão inativo"])
        self.assertEqual(consulta["total_compras"], Decimal("33.34"))

    def test_consulta_nao_cria_registros(self):
        compra = self._compra_historica()
        self._parcela(compra, "2026-10", 3, 6, "100.00", situacao=Situacao.REALIZADO)
        contagens_antes = (CompraCartao.objects.count(), ParcelaCartao.objects.count(), Fatura.objects.count())

        consultar_parcelas_futuras(self.usuario, ciclo="2026-10")

        self.assertEqual(
            (CompraCartao.objects.count(), ParcelaCartao.objects.count(), Fatura.objects.count()),
            contagens_antes,
        )


class ParcelasFuturasViewTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="titular", password="senha")
        self.client.force_login(self.usuario)

    def test_renderiza_a_composicao_da_referencia_sem_elementos_extras(self):
        resposta = self.client.get(reverse("parcelas"), {"cycle": "2026-10"})

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Parcelas conhecidas após 2026-10")
        self.assertContains(resposta, "Compras parceladas até o ciclo selecionado")
        self.assertContains(resposta, "Nenhuma parcela futura neste filtro.")
        self.assertContains(resposta, "Nenhuma parcela neste filtro.")
        self.assertContains(
            resposta,
            '<details class="panel full future-panel collapsible-panel future-purchases-panel"',
            html=False,
        )
        self.assertContains(
            resposta,
            '<details class="panel full future-panel collapsible-panel future-projections-panel"',
            html=False,
        )
        self.assertEqual(resposta.content.count(b" open>"), 2)
        conteudo = resposta.content.decode()
        self.assertLess(
            conteudo.index("Compras parceladas até o ciclo selecionado"),
            conteudo.index("Parcelas conhecidas após 2026-10"),
        )
        self.assertContains(resposta, "0 compras")
        self.assertContains(resposta, "R$ 0,00")
        self.assertNotContains(resposta, "Nova compra")
        self.assertNotContains(resposta, 'aria-label="Editar')
        self.assertNotContains(resposta, "<th>Ações</th>", html=False)
        self.assertNotContains(resposta, "Esta tela está reservada")
        self.assertContains(resposta, 'href="/parcelas/" class="active"', html=False)

    def test_parcelas_e_barras_futuras_usam_cor_de_saida(self):
        conta = Conta.objects.create(usuario=self.usuario, nome="Conta")
        cartao = Cartao.objects.create(
            usuario=self.usuario, nome="Cartão", conta_pagamento_padrao=conta, dia_vencimento=10
        )
        criar_compra_cartao(
            self.usuario,
            {
                "descricao": "Compra futura colorida",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 10, 5),
                "valor": Decimal("300.00"),
                "cartao": cartao,
                "categoria": None,
                "pessoa": None,
                "pessoa_nome_livre": "",
                "ambito": Ambito.PESSOAL,
                "situacao": Situacao.REALIZADO,
                "vencimento": None,
                "ciclo": "2026-10",
                "quantidade_parcelas": 3,
            },
        )

        resposta = self.client.get(reverse("parcelas"), {"cycle": "2026-10", "card": cartao.pk})

        self.assertContains(resposta, 'class="money amount-negative">R$ 100,00')
        self.assertContains(resposta, '.future-fill{height:100%;border-radius:10px;background:var(--danger)}')

    def test_lista_compras_exibe_dados_enriquecidos_e_totalizador(self):
        conta = Conta.objects.create(usuario=self.usuario, nome="Conta")
        cartao = Cartao.objects.create(
            usuario=self.usuario, nome="Cartão", conta_pagamento_padrao=conta, dia_vencimento=10
        )
        categoria = Categoria.objects.create(usuario=self.usuario, nome="Mercado")
        pessoa = Pessoa.objects.create(usuario=self.usuario, nome="Fornecedor")
        criar_compra_cartao(
            self.usuario,
            {
                "descricao": "Compra detalhada",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 10, 5),
                "valor": Decimal("300.00"),
                "cartao": cartao,
                "categoria": categoria,
                "pessoa": pessoa,
                "pessoa_nome_livre": "",
                "ambito": Ambito.PROFISSIONAL,
                "situacao": Situacao.REALIZADO,
                "vencimento": None,
                "ciclo": "2026-10",
                "quantidade_parcelas": 3,
            },
        )

        resposta = self.client.get(reverse("parcelas"), {"cycle": "2026-10", "card": cartao.pk})

        self.assertContains(resposta, "1 compra")
        self.assertContains(resposta, "R$ 100,00")
        self.assertContains(resposta, "05/10/2026")
        self.assertContains(resposta, "Compra detalhada")
        self.assertContains(resposta, "Parcela 1/3")
        self.assertContains(resposta, "Fornecedor • Profissional")
        self.assertContains(resposta, "Último ciclo: 2026-10")
        self.assertContains(resposta, "Mercado")
        self.assertContains(resposta, "Cobrado em fatura")
        self.assertNotContains(resposta, 'aria-label="Editar')
