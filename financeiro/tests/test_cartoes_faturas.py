from datetime import date
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import (
    Ambito,
    Cartao,
    Categoria,
    Conta,
    Fatura,
    NaturezaEvento,
    Pessoa,
    Situacao,
    Titulo,
)
from financeiro.services.cartoes_faturas import (
    aviso_ciclo_cartao,
    consultar_cartoes_faturas,
    criar_compra_cartao,
    editar_parcela_cartao,
    sincronizar_vencimentos_faturas_abertas_cartao,
)
from financeiro.services.dashboard import consultar_dashboard
from financeiro.vencimentos_cartao import calcular_vencimento_ciclo


class CartoesFaturasServiceTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="titular", password="senha")
        self.outro = get_user_model().objects.create_user(username="outro", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        self.outra_conta = Conta.objects.create(usuario=self.usuario, nome="Conta secundária", ativa=False)
        self.cartao = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão principal",
            conta_pagamento_padrao=self.conta,
            dia_vencimento=20,
        )
        self.outro_cartao = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão secundário",
            conta_pagamento_padrao=self.outra_conta,
            dia_vencimento=20,
            ativo=False,
        )
        self.categoria = Categoria.objects.create(usuario=self.usuario, nome="Mercado")
        self.pessoa = Pessoa.objects.create(usuario=self.usuario, nome="Fornecedor")

    def dados_compra(self, **alteracoes):
        dados = {
            "descricao": "Compra parcelada",
            "natureza": NaturezaEvento.DESPESA,
            "data_original": date(2026, 9, 10),
            "valor": Decimal("100.00"),
            "cartao": self.cartao,
            "categoria": self.categoria,
            "pessoa": self.pessoa,
            "pessoa_nome_livre": "",
            "ambito": Ambito.PESSOAL,
            "situacao": Situacao.REALIZADO,
            "vencimento": date(2026, 9, 20),
            "ciclo": "2026-09",
            "quantidade_parcelas": 3,
        }
        dados.update(alteracoes)
        return dados

    def test_parcelamento_distribui_centavos_e_projeta_ciclos(self):
        compra = criar_compra_cartao(self.usuario, self.dados_compra())

        parcelas = list(compra.parcelas.select_related("fatura").order_by("numero"))
        self.assertEqual([parcela.valor for parcela in parcelas], [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual([parcela.fatura.ciclo for parcela in parcelas], ["2026-09", "2026-10", "2026-11"])
        self.assertEqual(
            [parcela.vencimento for parcela in parcelas],
            [date(2026, 9, 20), date(2026, 10, 20), date(2026, 11, 20)],
        )
        self.assertEqual([parcela.situacao for parcela in parcelas], [Situacao.REALIZADO, Situacao.PREVISTO, Situacao.PREVISTO])
        self.assertEqual(sum((parcela.valor for parcela in parcelas), Decimal("0.00")), Decimal("100.00"))

    def test_calculo_ajusta_dias_29_30_e_31_ao_fim_do_mes(self):
        self.assertEqual(calcular_vencimento_ciclo("2027-02", 29), date(2027, 2, 28))
        self.assertEqual(calcular_vencimento_ciclo("2028-02", 30), date(2028, 2, 29))
        self.assertEqual(calcular_vencimento_ciclo("2026-04", 31), date(2026, 4, 30))

    def test_alteracao_do_dia_atualiza_somente_faturas_abertas_sem_vencimento_proprio(self):
        compra = criar_compra_cartao(self.usuario, self.dados_compra(quantidade_parcelas=2))
        primeira, segunda = list(compra.parcelas.select_related("fatura").order_by("numero"))
        primeira.fatura.status = Fatura.Status.FECHADA
        primeira.fatura.save(update_fields=["status"])

        self.cartao.dia_vencimento = 15
        self.cartao.save(update_fields=["dia_vencimento"])
        sincronizar_vencimentos_faturas_abertas_cartao(self.cartao)
        primeira.refresh_from_db()
        segunda.refresh_from_db()

        self.assertEqual(primeira.vencimento, date(2026, 9, 20))
        self.assertEqual(segunda.vencimento, date(2026, 10, 15))

    def test_consulta_usa_mesmo_conjunto_para_itens_e_totais(self):
        criar_compra_cartao(self.usuario, self.dados_compra())
        criar_compra_cartao(
            self.usuario,
            self.dados_compra(
                descricao="Crédito recebido",
                natureza=NaturezaEvento.ESTORNO,
                valor=Decimal("10.00"),
                quantidade_parcelas=1,
            ),
        )

        consulta = consultar_cartoes_faturas(self.usuario, ciclo="2026-09", cartao_id=self.cartao.pk)

        self.assertEqual(len(consulta["itens"]), 2)
        self.assertEqual(consulta["totais"]["debitos"], Decimal("33.34"))
        self.assertEqual(consulta["totais"]["creditos"], Decimal("10.00"))
        self.assertEqual(consulta["totais"]["liquido"], Decimal("23.34"))
        self.assertEqual(consulta["totais"]["parcelas"], Decimal("33.34"))
        self.assertEqual(consulta["totais"]["confirmado"], Decimal("23.34"))
        self.assertEqual(consulta["totais"]["projetado"], Decimal("23.34"))
        self.assertEqual(consulta["resumo_faturas"][0]["total_projetado"], Decimal("23.34"))
        dashboard = consultar_dashboard(self.usuario, periodo="2026-09", cartao_id=self.cartao.pk)
        self.assertEqual(dashboard["resumo"]["faturaProjetada"], consulta["totais"]["projetado"])

    def test_itens_sao_ordenados_por_data_original_e_id_do_lancamento(self):
        criar_compra_cartao(
            self.usuario,
            self.dados_compra(
                descricao="Data posterior",
                data_original=date(2026, 9, 12),
                quantidade_parcelas=1,
            ),
        )
        lancamento_id_menor = criar_compra_cartao(
            self.usuario,
            self.dados_compra(
                descricao="Mesma data, ID menor",
                data_original=date(2026, 9, 10),
                quantidade_parcelas=1,
            ),
        ).evento_id
        lancamento_id_maior = criar_compra_cartao(
            self.usuario,
            self.dados_compra(
                descricao="Mesma data, ID maior",
                data_original=date(2026, 9, 10),
                quantidade_parcelas=1,
            ),
        ).evento_id

        consulta = consultar_cartoes_faturas(self.usuario, ciclo="2026-09", cartao_id=self.cartao.pk)

        self.assertLess(lancamento_id_menor, lancamento_id_maior)
        self.assertEqual(
            [item["descricao"] for item in consulta["itens"]],
            ["Mesma data, ID menor", "Mesma data, ID maior", "Data posterior"],
        )

    def test_aviso_de_ciclo_usa_mes_de_pagamento_e_parcela(self):
        self.cartao.dia_fechamento = 25
        self.cartao.save(update_fields=["dia_fechamento"])

        self.assertEqual(aviso_ciclo_cartao(self.cartao, date(2026, 9, 1), "2026-10"), "")
        self.assertEqual(
            aviso_ciclo_cartao(self.cartao, date(2026, 6, 19), "2026-10", numero_parcela=4, total_parcelas=5),
            "",
        )
        self.assertEqual(aviso_ciclo_cartao(self.cartao, date(2026, 10, 8), "2026-11"), "")
        self.assertEqual(aviso_ciclo_cartao(self.cartao, date(2026, 10, 27), "2026-12"), "")
        self.assertEqual(
            aviso_ciclo_cartao(
                self.cartao,
                date(2026, 10, 8),
                "2026-11",
                vencimento=date(2026, 11, 11),
            ),
            "",
        )
        self.assertEqual(
            aviso_ciclo_cartao(self.cartao, date(2026, 12, 20), "2027-02", numero_parcela=2, total_parcelas=5),
            "",
        )

        aviso = aviso_ciclo_cartao(self.cartao, date(2026, 10, 27), "2026-11")
        self.assertIn("ciclo esperado é 12/2026", aviso)
        self.assertIn("data da compra (27/10/2026)", aviso)
        self.assertIn("foi informado 11/2026", aviso)
        self.assertIn("ciclo informado será mantido", aviso)

        self.cartao.dia_fechamento = None
        self.cartao.save(update_fields=["dia_fechamento"])
        self.assertEqual(aviso_ciclo_cartao(self.cartao, date(2026, 10, 27), "2026-10"), "")
        aviso_vencimento = aviso_ciclo_cartao(
            self.cartao,
            date(2026, 10, 27),
            "2026-10",
            vencimento=date(2026, 11, 11),
        )
        self.assertIn("vencimento (11/11/2026)", aviso_vencimento)
        self.assertIn("ciclo esperado é 11/2026", aviso_vencimento)

    def test_conta_restringe_cartoes_e_descarta_cartao_incompativel(self):
        consulta = consultar_cartoes_faturas(
            self.usuario,
            ciclo="2026-09",
            conta_id=self.conta.pk,
            cartao_id=self.outro_cartao.pk,
        )

        self.assertEqual(list(consulta["cartoes_compativeis"]), [self.cartao])
        self.assertIsNone(consulta["cartao_selecionado"])

    @patch("financeiro.services.cartoes_faturas.timezone.localdate", return_value=date(2026, 10, 6))
    def test_periodo_padrao_e_ciclo_disponivel_usam_mes_atual(self, _localdate):
        Fatura.objects.create(usuario=self.usuario, cartao=self.cartao, ciclo="2026-12")

        consulta_padrao = consultar_cartoes_faturas(self.usuario)
        consulta_escolhida = consultar_cartoes_faturas(self.usuario, ciclo="2026-12")

        self.assertEqual(consulta_padrao["ciclo_selecionado"], "2026-10")
        self.assertIn("2026-10", [ciclo["valor"] for ciclo in consulta_padrao["ciclos"]])
        self.assertEqual(consulta_escolhida["ciclo_selecionado"], "2026-12")

    def test_edicao_altera_somente_item_selecionado(self):
        compra = criar_compra_cartao(self.usuario, self.dados_compra())
        primeira, segunda = compra.parcelas.order_by("numero")[:2]
        descricao_segunda = segunda.descricao
        valor_segunda = segunda.valor

        editar_parcela_cartao(
            self.usuario,
            primeira.pk,
            {
                "descricao": "Somente a primeira parcela",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 9, 11),
                "valor": Decimal("30.00"),
                "cartao": self.cartao,
                "categoria": None,
                "pessoa": None,
                "pessoa_nome_livre": "Pessoa somente desta parcela",
                "ambito": Ambito.PROFISSIONAL,
                "situacao": Situacao.PREVISTO,
                "vencimento": None,
                "ciclo": "2026-09",
                "numero_parcela": 1,
                "total_parcelas": 3,
            },
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.descricao, "Somente a primeira parcela")
        self.assertEqual(primeira.valor, Decimal("30.00"))
        self.assertEqual(primeira.pessoa_nome_livre, "Pessoa somente desta parcela")
        self.assertEqual(segunda.descricao, descricao_segunda)
        self.assertEqual(segunda.pessoa, self.pessoa)
        self.assertEqual(segunda.pessoa_nome_livre, "")
        self.assertEqual(segunda.valor, valor_segunda)
        self.assertEqual(compra.evento.descricao, "Compra parcelada")

    def test_fatura_fechada_bloqueia_edicao(self):
        compra = criar_compra_cartao(self.usuario, self.dados_compra(quantidade_parcelas=1))
        parcela = compra.parcelas.select_related("fatura").get()
        parcela.fatura.status = Fatura.Status.FECHADA
        parcela.fatura.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            editar_parcela_cartao(
                self.usuario,
                parcela.pk,
                {
                    "descricao": parcela.descricao,
                    "natureza": parcela.natureza,
                    "data_original": parcela.data_original,
                    "valor": parcela.valor,
                    "cartao": self.cartao,
                    "categoria": parcela.categoria,
                    "pessoa": parcela.pessoa,
                    "ambito": parcela.ambito,
                    "situacao": parcela.situacao,
                    "vencimento": parcela.vencimento,
                    "ciclo": parcela.fatura.ciclo,
                    "numero_parcela": parcela.numero,
                    "total_parcelas": parcela.total,
                },
            )


class FaturaStatusMigrationTests(TestCase):
    def test_normaliza_somente_parcial_sem_titulo(self):
        usuario = get_user_model().objects.create_user(username="migracao", password="senha")
        conta = Conta.objects.create(usuario=usuario, nome="Conta")
        cartao = Cartao.objects.create(usuario=usuario, nome="Cartão", conta_pagamento_padrao=conta, dia_vencimento=10)
        sem_titulo = Fatura.objects.create(
            usuario=usuario, cartao=cartao, ciclo="2026-09", status=Fatura.Status.PARCIAL
        )
        com_titulo = Fatura.objects.create(
            usuario=usuario, cartao=cartao, ciclo="2026-10", status=Fatura.Status.PARCIAL
        )
        Titulo.objects.create(
            usuario=usuario,
            tipo=Titulo.Tipo.PAGAR,
            descricao="Fatura existente",
            vencimento=date(2026, 10, 20),
            valor_original=Decimal("100.00"),
            saldo_aberto=Decimal("50.00"),
            conta=conta,
            fatura=com_titulo,
        )

        migracao = import_module("financeiro.migrations.0009_normalizar_status_faturas_abertas")
        migracao.normalizar_faturas_parciais_sem_titulo(apps, None)
        sem_titulo.refresh_from_db()
        com_titulo.refresh_from_db()

        self.assertEqual(sem_titulo.status, Fatura.Status.ABERTA)
        self.assertEqual(com_titulo.status, Fatura.Status.PARCIAL)


class CartoesFaturasViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.usuario = user_model.objects.create_user(username="titular", password="senha")
        self.outro = user_model.objects.create_user(username="outro", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta")
        self.cartao = Cartao.objects.create(
            usuario=self.usuario, nome="Cartão", conta_pagamento_padrao=self.conta, dia_vencimento=10
        )
        self.cartao_outro = Cartao.objects.create(usuario=self.outro, nome="Cartão alheio", dia_vencimento=10)
        self.client.force_login(self.usuario)

    def dados_post(self, cartao=None, **alteracoes):
        dados = {
            "descricao": "Compra manual",
            "natureza": NaturezaEvento.DESPESA,
            "data_original": "2026-09-10",
            "valor": "100,00",
            "origem": "CARTAO",
            "cartao": (cartao or self.cartao).pk,
            "categoria": "",
            "pessoa": "",
            "ambito": Ambito.NAO_DEFINIDO,
            "situacao": Situacao.REALIZADO,
            "vencimento": "",
            "ciclo": "2026-09",
            "quantidade_parcelas": "2",
        }
        dados.update(alteracoes)
        return dados

    def criar_fatura(self, *, status=Fatura.Status.ABERTA, situacao=Situacao.REALIZADO):
        compra = criar_compra_cartao(
            self.usuario,
            {
                "descricao": "Compra da fatura",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 9, 10),
                "valor": Decimal("100.00"),
                "cartao": self.cartao,
                "categoria": None,
                "pessoa": None,
                "pessoa_nome_livre": "",
                "ambito": Ambito.PESSOAL,
                "situacao": situacao,
                "vencimento": date(2026, 9, 20),
                "ciclo": "2026-09",
                "quantidade_parcelas": 1,
            },
        )
        fatura = compra.parcelas.select_related("fatura").get().fatura
        if fatura.status != status:
            fatura.status = status
            fatura.save(update_fields=["status"])
        return fatura

    def criar_titulo(self, fatura, *, saldo=Decimal("100.00")):
        return Titulo.objects.create(
            usuario=self.usuario,
            tipo=Titulo.Tipo.PAGAR,
            descricao="Fatura Cartão 2026-09",
            vencimento=date(2026, 9, 20),
            valor_original=Decimal("100.00"),
            saldo_aberto=saldo,
            status=Titulo.Status.LIQUIDADO if saldo == 0 else Titulo.Status.ABERTO,
            conta=self.conta,
            fatura=fatura,
            ativo=saldo > 0,
        )

    def abrir_painel(self, fatura):
        return self.client.get(
            reverse("cartoes_faturas"),
            {"cycle": fatura.ciclo, "card": self.cartao.pk, "invoice": fatura.pk},
        )

    def test_tela_renderiza_estrutura_da_referencia(self):
        resposta = self.client.get(reverse("cartoes_faturas"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cartões e faturas")
        self.assertContains(resposta, "Débitos projetados")
        self.assertContains(resposta, "Itens da fatura")
        self.assertContains(resposta, "Fechamento e pagamento")
        self.assertContains(resposta, "Nenhum item neste filtro.")

    def test_formulario_de_compra_nao_expoe_vencimento_editavel(self):
        resposta = self.client.get(reverse("compra_cartao_nova"))

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'name="vencimento"')

    def test_edicao_do_cartao_sincroniza_parcela_de_fatura_aberta(self):
        compra = criar_compra_cartao(
            self.usuario,
            {
                "descricao": "Compra aberta",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 9, 10),
                "valor": Decimal("50.00"),
                "cartao": self.cartao,
                "categoria": None,
                "pessoa": None,
                "pessoa_nome_livre": "",
                "ambito": Ambito.PESSOAL,
                "situacao": Situacao.REALIZADO,
                "ciclo": "2026-09",
                "quantidade_parcelas": 1,
            },
        )

        resposta = self.client.post(
            reverse("cartao_editar", args=[self.cartao.pk]),
            {
                "nome": self.cartao.nome,
                "emissor": "",
                "identificador_externo": "",
                "final": "",
                "dia_fechamento": "",
                "dia_vencimento": "15",
                "conta_pagamento_padrao": self.conta.pk,
                "limite": "0,00",
                "ativo": "on",
            },
        )

        self.assertRedirects(resposta, reverse("cartoes"))
        self.assertEqual(compra.parcelas.get().vencimento, date(2026, 9, 15))

    def test_fatura_colore_debitos_creditos_e_total_exigido(self):
        fatura = self.criar_fatura()
        criar_compra_cartao(
            self.usuario,
            {
                "descricao": "Crédito da fatura",
                "natureza": NaturezaEvento.ESTORNO,
                "data_original": date(2026, 9, 12),
                "valor": Decimal("20.00"),
                "cartao": self.cartao,
                "categoria": None,
                "pessoa": None,
                "pessoa_nome_livre": "",
                "ambito": Ambito.PESSOAL,
                "situacao": Situacao.REALIZADO,
                "vencimento": date(2026, 9, 20),
                "ciclo": "2026-09",
                "quantidade_parcelas": 1,
            },
        )

        resposta = self.abrir_painel(fatura)

        self.assertContains(resposta, 'class="money amount-negative">-R$ 100,00')
        self.assertContains(resposta, 'class="money amount-positive">R$ 20,00')
        self.assertContains(resposta, 'class="value amount-negative">R$ 80,00')

    def test_fatura_aberta_exibe_acao_de_fechamento(self):
        fatura = self.criar_fatura()

        resposta = self.abrir_painel(fatura)

        self.assertContains(resposta, "A composição está pronta para conferência e fechamento.")
        self.assertContains(resposta, "Conferir e fechar")
        self.assertNotContains(resposta, "Programar pagamento")
        self.assertContains(resposta, '<details class="panel full invoice-items collapsible-panel">')
        self.assertNotContains(resposta, 'class="panel full invoice-items collapsible-panel" open')
        self.assertContains(resposta, 'class="collapsible-summary"')
        self.assertContains(resposta, 'class="icon-button icon-edit"')
        self.assertContains(resposta, 'aria-label="Editar item da fatura"')

    def test_fatura_com_previsao_explica_bloqueio_e_nao_exibe_fechamento(self):
        fatura = self.criar_fatura(situacao=Situacao.PREVISTO)

        resposta = self.abrir_painel(fatura)

        self.assertContains(resposta, "Há 1 previsão(ões) pendente(s)")
        self.assertNotContains(resposta, 'data-modal-title="Conferir e fechar fatura"')

    def test_fatura_fechada_exibe_acoes_de_pagamento_e_reabertura(self):
        fatura = self.criar_fatura(status=Fatura.Status.FECHADA)
        self.criar_titulo(fatura)

        resposta = self.abrir_painel(fatura)

        self.assertContains(resposta, "Programar pagamento")
        self.assertContains(resposta, "Conciliar pagamento")
        self.assertContains(resposta, "Registrar pagamento manual")
        self.assertContains(resposta, "Transportar saldo")
        self.assertContains(resposta, "Reabrir/Corrigir fechamento")
        self.assertNotContains(resposta, 'data-modal-title="Conferir e fechar fatura"')

    def test_fatura_paga_exibe_historico_e_reabertura_sem_novo_pagamento(self):
        fatura = self.criar_fatura(status=Fatura.Status.PAGA)
        self.criar_titulo(fatura, saldo=Decimal("0.00"))

        resposta = self.abrir_painel(fatura)

        self.assertContains(resposta, "A fatura está paga")
        self.assertContains(resposta, "Reabrir/Corrigir fechamento")
        self.assertNotContains(resposta, "Programar pagamento")

    def test_reabertura_exige_motivo_e_registra_historico(self):
        fatura = self.criar_fatura(status=Fatura.Status.FECHADA)
        self.criar_titulo(fatura)
        url = reverse("fatura_reabrir", args=[fatura.pk])

        resposta_get = self.client.get(url)
        resposta_invalida = self.client.post(url, {"motivo": ""})
        fatura.refresh_from_db()

        self.assertContains(resposta_get, "Motivo da reabertura ou correção")
        self.assertEqual(resposta_invalida.status_code, 200)
        self.assertEqual(fatura.status, Fatura.Status.FECHADA)

        resposta = self.client.post(url, {"motivo": "Valor importado incorretamente."})
        fatura.refresh_from_db()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(fatura.status, Fatura.Status.ABERTA)
        self.assertEqual(fatura.historico.get().dados["motivo"], "Valor importado incorretamente.")

    def test_nova_compra_persiste_e_redireciona_para_ciclo(self):
        resposta = self.client.post(reverse("compra_cartao_nova"), self.dados_post())

        self.assertRedirects(resposta, f"{reverse('cartoes_faturas')}?cycle=2026-09&card={self.cartao.pk}")
        self.assertEqual(self.cartao.compracartao_set.count(), 1)
        self.assertEqual(self.cartao.compracartao_set.get().parcelas.count(), 2)

    def test_nova_compra_recorrente_cria_compras_independentes(self):
        resposta = self.client.post(
            reverse("compra_cartao_nova"),
            self.dados_post(
                modo_lancamento="RECORRENTE",
                quantidade_parcelas="1",
                quantidade_repeticoes="3",
                intervalo_meses="1",
                valor="120,00",
            ),
        )

        self.assertRedirects(resposta, f"{reverse('cartoes_faturas')}?cycle=2026-09&card={self.cartao.pk}")
        compras = list(self.cartao.compracartao_set.order_by("evento__numero_recorrencia"))
        self.assertEqual(len(compras), 3)
        self.assertEqual([compra.parcelas.get().valor for compra in compras], [Decimal("120.00")] * 3)
        self.assertEqual([compra.parcelas.get().fatura.ciclo for compra in compras], ["2026-09", "2026-10", "2026-11"])

    def test_novo_lancamento_nao_aceita_cartao_de_outro_usuario(self):
        resposta = self.client.post(reverse("compra_cartao_nova"), self.dados_post(cartao=self.cartao_outro))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Faça uma escolha válida")
        self.assertEqual(self.cartao.compracartao_set.count(), 0)

    def test_edicao_de_parcela_de_outro_usuario_retorna_404(self):
        conta_outro = Conta.objects.create(usuario=self.outro, nome="Conta alheia")
        self.cartao_outro.conta_pagamento_padrao = conta_outro
        self.cartao_outro.save(update_fields=["conta_pagamento_padrao"])
        compra = criar_compra_cartao(
            self.outro,
            {
                "descricao": "Compra alheia",
                "natureza": NaturezaEvento.DESPESA,
                "data_original": date(2026, 9, 1),
                "valor": Decimal("20.00"),
                "cartao": self.cartao_outro,
                "categoria": None,
                "pessoa": None,
                "ambito": Ambito.NAO_DEFINIDO,
                "situacao": Situacao.REALIZADO,
                "vencimento": None,
                "ciclo": "2026-09",
                "quantidade_parcelas": 1,
            },
        )

        resposta = self.client.get(reverse("parcela_cartao_editar", args=[compra.parcelas.get().pk]))

        self.assertEqual(resposta.status_code, 404)
