from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Ambito, Categoria, Orcamento


class OrcamentosViewsTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="orcamentos", password="senha")
        self.outro_usuario = get_user_model().objects.create_user(username="orcamentos-outro", password="senha")
        self.categoria = Categoria.objects.create(usuario=self.usuario, nome="Alimentação")
        self.categoria_filha = Categoria.objects.create(
            usuario=self.usuario,
            nome="Restaurantes",
            categoria_pai=self.categoria,
        )
        self.categoria_outra = Categoria.objects.create(usuario=self.usuario, nome="Moradia")
        self.categoria_receita = Categoria.objects.create(
            usuario=self.usuario,
            nome="Salário",
            tipo=Categoria.Tipo.RECEITA,
        )
        self.categoria_inativa = Categoria.objects.create(
            usuario=self.usuario,
            nome="Despesa antiga",
            ativa=False,
        )
        self.categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria externa")
        self.client.force_login(self.usuario)

    def criar_orcamento(self, **kwargs):
        dados = {
            "usuario": self.usuario,
            "categoria": self.categoria,
            "mes": "2026-10",
            "ambito": Ambito.PESSOAL,
            "limite": "500.00",
        }
        dados.update(kwargs)
        return Orcamento.objects.create(**dados)

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 21))
    def test_lista_aplica_mes_atual_somente_na_abertura_inicial(self, _localdate):
        atual = self.criar_orcamento()
        anterior = self.criar_orcamento(mes="2026-09", ambito=Ambito.PROFISSIONAL)

        resposta_inicial = self.client.get(reverse("orcamentos"))
        resposta_todos = self.client.get(reverse("orcamentos"), {"mes": ""})

        self.assertContains(resposta_inicial, "10/2026")
        self.assertNotContains(resposta_inicial, "09/2026")
        self.assertEqual(list(resposta_inicial.context["orcamentos"]), [atual])
        self.assertEqual(set(resposta_todos.context["orcamentos"]), {atual, anterior})
        self.assertEqual(resposta_inicial.context["mes_filtro"], "10/2026")

    def test_filtros_por_categoria_mes_e_ambito_sao_combinados(self):
        esperado = self.criar_orcamento(mes="2026-11", ambito=Ambito.PROFISSIONAL)
        self.criar_orcamento(categoria=self.categoria_outra, mes="2026-11", ambito=Ambito.PESSOAL)
        self.criar_orcamento(mes="2026-12", ambito=Ambito.PROFISSIONAL)

        resposta = self.client.get(
            reverse("orcamentos"),
            {"categoria": self.categoria.pk, "mes": "11/2026", "ambito": Ambito.PROFISSIONAL},
        )

        self.assertEqual(list(resposta.context["orcamentos"]), [esperado])
        self.assertContains(resposta, "Alimentação")
        self.assertEqual(resposta.context["mes_filtro"], "11/2026")

    def test_layout_dos_filtros_prioriza_categoria_ambito_e_periodo_compacto(self):
        resposta = self.client.get(reverse("orcamentos"), {"mes": ""})
        conteudo = resposta.content.decode()

        self.assertContains(resposta, "budget-filter-category")
        self.assertContains(resposta, "budget-filter-scope")
        self.assertContains(resposta, "budget-filter-period")
        self.assertLess(conteudo.index('name="categoria"'), conteudo.index('name="ambito"'))
        self.assertLess(conteudo.index('name="ambito"'), conteudo.index('name="mes"'))
        self.assertContains(resposta, 'data-temporal-control="month"')
        self.assertContains(resposta, 'data-open-temporal-picker aria-label="Abrir seletor de período"')
        self.assertContains(resposta, 'class="temporal-native" type="month"')
        self.assertIn("visible.value.replace(/\\D/g, '').slice(0, 6)", conteudo)
        self.assertIn("digits.slice(0, 2), digits.slice(2, 6)", conteudo)

    def test_listagem_nao_expoe_orcamentos_de_outro_usuario(self):
        proprio = self.criar_orcamento()
        alheio = Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=self.categoria_outro,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="900.00",
        )

        resposta = self.client.get(reverse("orcamentos"), {"mes": ""})

        self.assertEqual(list(resposta.context["orcamentos"]), [proprio])
        self.assertNotContains(resposta, str(alheio.limite))

    def test_criacao_converte_mes_e_aceita_valor_brasileiro(self):
        resposta = self.client.post(
            reverse("orcamento_novo"),
            {
                "categoria": self.categoria.pk,
                "mes": "11/2026",
                "ambito": Ambito.PROFISSIONAL,
                "limite": "1.234,56",
            },
        )

        self.assertRedirects(resposta, reverse("orcamentos"))
        criado = Orcamento.objects.get(categoria=self.categoria)
        self.assertEqual(criado.usuario, self.usuario)
        self.assertEqual(criado.mes, "2026-11")
        self.assertEqual(str(criado.limite), "1234.56")

    def test_formulario_restringe_categorias_e_preserva_inativa_na_edicao(self):
        orcamento = self.criar_orcamento(categoria=self.categoria_inativa)

        novo = self.client.get(reverse("orcamento_novo"))
        edicao = self.client.get(reverse("orcamento_editar", args=[orcamento.pk]))

        self.assertContains(novo, self.categoria.nome)
        self.assertNotContains(novo, self.categoria_filha.nome)
        self.assertNotContains(novo, self.categoria_receita.nome)
        self.assertNotContains(novo, self.categoria_inativa.nome)
        self.assertNotContains(novo, self.categoria_outro.nome)
        self.assertContains(edicao, self.categoria_inativa.nome)

    def test_formularios_usam_seletor_de_mes_ano_com_mascara_compartilhada(self):
        orcamento = self.criar_orcamento()
        respostas = (
            self.client.get(reverse("orcamento_novo")),
            self.client.get(reverse("orcamento_editar", args=[orcamento.pk])),
            self.client.get(reverse("orcamento_clonar", args=[orcamento.pk])),
        )

        for resposta in respostas:
            with self.subTest(url=resposta.request["PATH_INFO"]):
                conteudo = resposta.content.decode()
                self.assertContains(resposta, 'data-temporal-control="month"')
                self.assertContains(resposta, 'class="temporal-native" type="month"')
                self.assertContains(resposta, 'data-open-temporal-picker aria-label="Abrir seletor de mês"')
                self.assertIn("visible.value.replace(/\\D/g, '').slice(0, 6)", conteudo)

    def test_categoria_com_superior_nao_pode_receber_orcamento_direto(self):
        resposta = self.client.post(
            reverse("orcamento_novo"),
            {
                "categoria": self.categoria_filha.pk,
                "mes": "11/2026",
                "ambito": Ambito.PESSOAL,
                "limite": "300,00",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Faça uma escolha válida")
        self.assertFalse(Orcamento.objects.filter(categoria=self.categoria_filha).exists())

    def test_novo_sugere_mes_filtrado_e_mutacoes_preservam_filtros(self):
        filtros = "?categoria=&mes=11%2F2026&ambito=PROFISSIONAL"
        pagina = self.client.get(f"{reverse('orcamentos')}?mes=11%2F2026&ambito=PROFISSIONAL")
        novo = self.client.get(f"{reverse('orcamento_novo')}{filtros}")

        self.assertContains(pagina, f'{reverse("orcamento_novo")}?categoria=&amp;mes=11%2F2026&amp;ambito=PROFISSIONAL')
        self.assertContains(novo, 'value="11/2026"')

        criado = self.client.post(
            f"{reverse('orcamento_novo')}{filtros}",
            {
                "categoria": self.categoria.pk,
                "mes": "11/2026",
                "ambito": Ambito.PROFISSIONAL,
                "limite": "300,00",
            },
        )
        self.assertEqual(criado.url, f"{reverse('orcamentos')}{filtros}")

        orcamento = Orcamento.objects.get(categoria=self.categoria, mes="2026-11")
        editado = self.client.post(
            f"{reverse('orcamento_editar', args=[orcamento.pk])}{filtros}",
            {
                "categoria": self.categoria.pk,
                "mes": "11/2026",
                "ambito": Ambito.PROFISSIONAL,
                "limite": "350,00",
            },
        )
        self.assertEqual(editado.url, f"{reverse('orcamentos')}{filtros}")

        excluido = self.client.post(f"{reverse('orcamento_excluir', args=[orcamento.pk])}{filtros}")
        self.assertEqual(excluido.url, f"{reverse('orcamentos')}{filtros}")

    def test_edicao_e_acesso_a_registro_alheio_retornam_404(self):
        orcamento = self.criar_orcamento()
        alheio = Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=self.categoria_outro,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="100.00",
        )

        resposta = self.client.post(
            reverse("orcamento_editar", args=[orcamento.pk]),
            {
                "categoria": self.categoria.pk,
                "mes": "12/2026",
                "ambito": Ambito.PESSOAL,
                "limite": "700,00",
            },
        )

        self.assertRedirects(resposta, reverse("orcamentos"))
        orcamento.refresh_from_db()
        self.assertEqual(orcamento.mes, "2026-12")
        self.assertEqual(self.client.get(reverse("orcamento_editar", args=[alheio.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("orcamento_clonar", args=[alheio.pk])).status_code, 404)

    def test_duplicidade_exibe_mensagem_amigavel(self):
        self.criar_orcamento()

        resposta = self.client.post(
            reverse("orcamento_novo"),
            {
                "categoria": self.categoria.pk,
                "mes": "10/2026",
                "ambito": Ambito.PESSOAL,
                "limite": "600,00",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Já existe um orçamento para esta categoria, mês e âmbito.")
        self.assertEqual(Orcamento.objects.count(), 1)

    def test_clonagem_preenche_proximo_mes_e_salva_novo_registro(self):
        origem = self.criar_orcamento(mes="2026-10", limite="321.45")

        formulario = self.client.get(reverse("orcamento_clonar", args=[origem.pk]))
        resposta = self.client.post(
            reverse("orcamento_clonar", args=[origem.pk]),
            {
                "categoria": self.categoria.pk,
                "mes": "11/2026",
                "ambito": Ambito.PESSOAL,
                "limite": "321,45",
            },
        )

        self.assertContains(formulario, 'value="11/2026"')
        self.assertRedirects(resposta, reverse("orcamentos"))
        self.assertTrue(Orcamento.objects.filter(usuario=self.usuario, mes="2026-11", limite="321.45").exists())

    def test_clonagem_de_dezembro_avanca_para_janeiro(self):
        origem = self.criar_orcamento(mes="2026-12")

        resposta = self.client.get(reverse("orcamento_clonar", args=[origem.pk]))

        self.assertContains(resposta, 'value="01/2027"')

    def test_exclusao_exige_post_e_respeita_usuario(self):
        proprio = self.criar_orcamento()
        alheio = Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=self.categoria_outro,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="100.00",
        )

        self.assertEqual(self.client.get(reverse("orcamento_excluir", args=[proprio.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("orcamento_excluir", args=[alheio.pk])).status_code, 404)
        resposta = self.client.post(reverse("orcamento_excluir", args=[proprio.pk]), follow=True)

        self.assertFalse(Orcamento.objects.filter(pk=proprio.pk).exists())
        self.assertTrue(Orcamento.objects.filter(pk=alheio.pk).exists())
        self.assertContains(resposta, "Orçamento excluído.")

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    def test_lista_exibe_clonagem_de_periodo_ao_lado_do_novo_orcamento(self, _localdate):
        resposta = self.client.get(reverse("orcamentos"))
        conteudo = resposta.content.decode()

        self.assertContains(resposta, reverse("orcamentos_importar_despesas"))
        self.assertContains(resposta, "Importar valores")
        self.assertContains(resposta, reverse("orcamentos_clonar_periodo"))
        self.assertContains(resposta, "Clonar período")
        self.assertContains(resposta, "Novo orçamento")
        self.assertLess(conteudo.index("Importar valores"), conteudo.index("Clonar período"))
        self.assertLess(conteudo.index("Clonar período"), conteudo.index("Novo orçamento"))
        self.assertContains(resposta, 'data-modal-title="Importar valores para o orçamento"')
        self.assertContains(resposta, "data-modal-title=\"Clonar período de orçamento\"")

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    def test_modal_importacao_sugere_periodos_e_limita_origem_ao_mes_atual(self, _localdate):
        atual = self.client.get(reverse("orcamentos_importar_despesas"))
        futuro = self.client.get(reverse("orcamentos_importar_despesas"), {"mes": "12/2026"})

        self.assertContains(atual, 'name="mes_despesas" value="09/2026"')
        self.assertContains(atual, 'name="mes_destino" value="10/2026"')
        self.assertContains(futuro, 'name="mes_despesas" value="10/2026"')
        self.assertContains(futuro, 'name="mes_destino" value="12/2026"')
        self.assertContains(futuro, 'data-temporal-control="month"', count=2)
        self.assertContains(futuro, 'class="temporal-native" type="month"', count=2)
        self.assertContains(futuro, "Abrir seletor do período das despesas")
        self.assertContains(futuro, "Abrir seletor do período de destino")
        self.assertContains(futuro, "data-close-dialog")

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    def test_importacao_rejeita_origem_futura_e_destino_nao_posterior(self, _localdate):
        origem_futura = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "11/2026", "mes_destino": "12/2026", "acao": "revisar"},
        )
        destino_invalido = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "10/2026", "mes_destino": "10/2026", "acao": "revisar"},
        )

        self.assertContains(origem_futura, "não pode ser posterior ao mês atual")
        self.assertContains(destino_invalido, "deve ser posterior ao período das despesas")
        self.assertFalse(Orcamento.objects.filter(usuario=self.usuario).exists())

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    def test_revisao_importacao_sem_despesas_nao_oferece_execucao(self, _localdate):
        resposta = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(resposta, "Nenhuma despesa elegível foi encontrada em 10/2026")
        self.assertNotContains(resposta, 'value="completa"')
        self.assertNotContains(resposta, 'value="parcial"')

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    @patch("financeiro.views.previsualizar_importacao_despesas")
    def test_revisao_importacao_destino_ocupado_exibe_acoes_e_contagens(
        self,
        previsualizar,
        _localdate,
    ):
        previsualizar.return_value = {
            "mes_despesas": "2026-10",
            "mes_destino": "2026-11",
            "itens": [],
            "quantidade_importavel": 2,
            "valor_importavel": Decimal("350.00"),
            "quantidade_ignorados": 1,
            "ignorados": {
                "sem_categoria": {"quantidade": 1, "valor": Decimal("25.00")},
                "categoria_inativa": {"quantidade": 0, "valor": Decimal("0.00")},
                "nao_positivos": {"quantidade": 0, "valor": Decimal("0.00")},
            },
            "quantidade_destino": 1,
            "quantidade_faltantes": 1,
            "quantidade_ja_existentes": 1,
        }

        resposta = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(resposta, "R$ 350,00")
        self.assertContains(resposta, "Combinações faltantes")
        self.assertContains(resposta, "Itens ignorados: 1")
        self.assertContains(resposta, "Substituir e importar tudo")
        self.assertContains(resposta, "Importar somente faltantes")
        self.assertContains(resposta, 'value="completa"')
        self.assertContains(resposta, 'value="parcial"')

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    @patch("financeiro.views.previsualizar_importacao_despesas")
    def test_revisao_importacao_desabilita_parcial_quando_nada_esta_faltando(
        self,
        previsualizar,
        _localdate,
    ):
        previsualizar.return_value = {
            "mes_despesas": "2026-10",
            "mes_destino": "2026-11",
            "itens": [],
            "quantidade_importavel": 1,
            "valor_importavel": Decimal("100.00"),
            "quantidade_ignorados": 0,
            "ignorados": {
                "sem_categoria": {"quantidade": 0, "valor": Decimal("0.00")},
                "categoria_inativa": {"quantidade": 0, "valor": Decimal("0.00")},
                "nao_positivos": {"quantidade": 0, "valor": Decimal("0.00")},
            },
            "quantidade_destino": 1,
            "quantidade_faltantes": 0,
            "quantidade_ja_existentes": 1,
        }

        resposta = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(
            resposta,
            'value="parcial" disabled aria-disabled="true"',
        )

    @patch("financeiro.views.timezone.localdate", return_value=date(2026, 10, 22))
    @patch("financeiro.views.importar_despesas_para_orcamento")
    def test_confirmacao_importacao_ajax_envia_acao_e_redireciona_para_destino(
        self,
        importar,
        _localdate,
    ):
        importar.return_value = {
            "modo": "completa",
            "incluidos": 2,
            "substituidos": 1,
            "preservados": 0,
            "ignorados": 1,
            "valor_importado": Decimal("350.00"),
        }

        resposta = self.client.post(
            reverse("orcamentos_importar_despesas"),
            {"mes_despesas": "10/2026", "mes_destino": "11/2026", "acao": "completa"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        importar.assert_called_once_with(self.usuario, "2026-10", "2026-11", "completa")
        self.assertEqual(
            resposta.url,
            f"{reverse('orcamentos')}?categoria=&mes=11%2F2026&ambito=",
        )

    def test_modal_sugere_origem_filtrada_destino_seguinte_e_seletores_mensais(self):
        resposta = self.client.get(reverse("orcamentos_clonar_periodo"), {"mes": "12/2026"})

        self.assertContains(resposta, 'name="mes_origem" value="12/2026"')
        self.assertContains(resposta, 'name="mes_destino" value="01/2027"')
        self.assertContains(resposta, 'data-temporal-control="month"', count=2)
        self.assertContains(resposta, 'class="temporal-native" type="month"', count=2)
        self.assertContains(resposta, "Abrir seletor de período de origem")
        self.assertContains(resposta, "Abrir seletor de período de destino")
        self.assertContains(resposta, "data-close-dialog")
        self.assertIn("const formData = new FormData(form);", resposta.content.decode())
        self.assertIn("if (event.submitter?.name)", resposta.content.decode())
        self.assertIn(
            "formData.set(event.submitter.name, event.submitter.value);",
            resposta.content.decode(),
        )

    def test_revisao_informa_origem_vazia_sem_oferecer_clonagem(self):
        Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=self.categoria_outro,
            mes="2026-10",
            ambito=Ambito.PESSOAL,
            limite="900.00",
        )

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(resposta, "Nenhum orçamento foi encontrado no período de origem 10/2026")
        self.assertNotContains(resposta, 'value="completa"')
        self.assertNotContains(resposta, 'value="parcial"')
        self.assertEqual(Orcamento.objects.filter(usuario=self.usuario).count(), 0)

    def test_clonagem_periodo_rejeita_periodos_iguais_e_acao_invalida(self):
        origem = self.criar_orcamento()

        periodos_iguais = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "10/2026", "acao": "revisar"},
        )
        acao_invalida = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "desconhecida"},
        )

        self.assertContains(periodos_iguais, "O período de destino deve ser diferente do período de origem")
        self.assertContains(acao_invalida, "Escolha uma ação válida para continuar")
        self.assertEqual(Orcamento.objects.filter(usuario=self.usuario).count(), 1)
        self.assertTrue(Orcamento.objects.filter(pk=origem.pk).exists())

    def test_revisao_de_destino_ocupado_exibe_opcoes_e_contagens(self):
        self.criar_orcamento()
        self.criar_orcamento(
            categoria=self.categoria_outra,
            ambito=Ambito.PROFISSIONAL,
            limite="700.00",
        )
        self.criar_orcamento(mes="2026-11", limite="999.00")

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(resposta, "A origem contém <strong>2</strong> orçamento(s)")
        self.assertContains(resposta, "O destino já contém <strong>1</strong> registro(s)")
        self.assertContains(resposta, "<strong>1</strong> combinação(ões)")
        self.assertContains(resposta, 'value="completa"')
        self.assertContains(resposta, 'value="parcial"')
        self.assertContains(resposta, "Substituir e clonar tudo")
        self.assertContains(resposta, "Clonar somente faltantes")

    def test_clonagem_completa_substitui_destino_e_preserva_outro_usuario(self):
        self.criar_orcamento(limite="321.45")
        self.criar_orcamento(
            categoria=self.categoria_outra,
            ambito=Ambito.PROFISSIONAL,
            limite="654.32",
        )
        destino_antigo = self.criar_orcamento(
            mes="2026-11",
            categoria=self.categoria_outra,
            ambito=Ambito.PESSOAL,
            limite="999.00",
        )
        destino_alheio = Orcamento.objects.create(
            usuario=self.outro_usuario,
            categoria=self.categoria_outro,
            mes="2026-11",
            ambito=Ambito.PESSOAL,
            limite="888.00",
        )

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "completa"},
        )

        self.assertEqual(
            resposta.url,
            f"{reverse('orcamentos')}?categoria=&mes=11%2F2026&ambito=",
        )
        self.assertFalse(Orcamento.objects.filter(pk=destino_antigo.pk).exists())
        self.assertTrue(Orcamento.objects.filter(pk=destino_alheio.pk).exists())
        clonados = set(
            Orcamento.objects.filter(usuario=self.usuario, mes="2026-11").values_list(
                "categoria_id", "ambito", "limite"
            )
        )
        self.assertEqual(
            clonados,
            {
                (self.categoria.pk, Ambito.PESSOAL, Decimal("321.45")),
                (self.categoria_outra.pk, Ambito.PROFISSIONAL, Decimal("654.32")),
            },
        )

    def test_clonagem_completa_copia_origem_para_destino_vazio(self):
        origem = self.criar_orcamento(limite="432.10")

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "completa"},
        )

        self.assertEqual(resposta.status_code, 302)
        clonado = Orcamento.objects.get(usuario=self.usuario, mes="2026-11")
        self.assertNotEqual(clonado.pk, origem.pk)
        self.assertEqual(clonado.categoria, origem.categoria)
        self.assertEqual(clonado.ambito, origem.ambito)
        self.assertEqual(clonado.limite, Decimal("432.10"))

    def test_clonagem_parcial_usa_categoria_e_ambito_e_preserva_destino(self):
        self.criar_orcamento(limite="100.00")
        self.criar_orcamento(ambito=Ambito.PROFISSIONAL, limite="200.00")
        self.criar_orcamento(categoria=self.categoria_outra, limite="300.00")
        existente = self.criar_orcamento(mes="2026-11", limite="999.00")
        extra = self.criar_orcamento(
            categoria=self.categoria_outra,
            mes="2026-11",
            ambito=Ambito.PROFISSIONAL,
            limite="777.00",
        )

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "parcial"},
        )

        self.assertEqual(resposta.status_code, 302)
        existente.refresh_from_db()
        extra.refresh_from_db()
        self.assertEqual(str(existente.limite), "999.00")
        self.assertEqual(str(extra.limite), "777.00")
        self.assertEqual(Orcamento.objects.filter(usuario=self.usuario, mes="2026-11").count(), 4)
        self.assertTrue(
            Orcamento.objects.filter(
                usuario=self.usuario,
                categoria=self.categoria,
                mes="2026-11",
                ambito=Ambito.PROFISSIONAL,
                limite="200.00",
            ).exists()
        )
        self.assertTrue(
            Orcamento.objects.filter(
                usuario=self.usuario,
                categoria=self.categoria_outra,
                mes="2026-11",
                ambito=Ambito.PESSOAL,
                limite="300.00",
            ).exists()
        )

    def test_revisao_desabilita_parcial_quando_nao_ha_categoria_faltante(self):
        self.criar_orcamento()
        self.criar_orcamento(mes="2026-11", limite="600.00")

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )

        self.assertContains(
            resposta,
            'value="parcial" disabled aria-disabled="true"',
        )

    def test_confirmacao_revalida_destino_alterado_apos_revisao(self):
        self.criar_orcamento(limite="500.00")
        revisao = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "revisar"},
        )
        self.assertContains(revisao, "O período de destino está vazio")
        concorrente = self.criar_orcamento(mes="2026-11", limite="900.00")

        resposta = self.client.post(
            reverse("orcamentos_clonar_periodo"),
            {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "completa"},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Orcamento.objects.filter(pk=concorrente.pk).exists())
        self.assertTrue(
            Orcamento.objects.filter(usuario=self.usuario, mes="2026-11", limite="500.00").exists()
        )

    def test_erro_na_copia_desfaz_exclusao_do_destino(self):
        self.criar_orcamento(limite="500.00")
        destino = self.criar_orcamento(mes="2026-11", limite="900.00")

        with patch(
            "financeiro.services.orcamentos.Orcamento.objects.bulk_create",
            side_effect=IntegrityError("conflito simulado"),
        ):
            resposta = self.client.post(
                reverse("orcamentos_clonar_periodo"),
                {"mes_origem": "10/2026", "mes_destino": "11/2026", "acao": "completa"},
            )

        self.assertContains(resposta, "Os orçamentos foram alterados durante a confirmação")
        destino.refresh_from_db()
        self.assertEqual(str(destino.limite), "900.00")

    def test_menu_fica_entre_parcelas_e_importacao_e_permanece_ativo(self):
        orcamento = self.criar_orcamento()
        lista = self.client.get(reverse("orcamentos")).content.decode()
        edicao = self.client.get(reverse("orcamento_editar", args=[orcamento.pk])).content.decode()
        clonagem = self.client.get(reverse("orcamento_clonar", args=[orcamento.pk])).content.decode()
        clonagem_periodo = self.client.get(reverse("orcamentos_clonar_periodo")).content.decode()
        importacao_despesas = self.client.get(reverse("orcamentos_importar_despesas")).content.decode()

        self.assertLess(lista.index(">Parcelas futuras</span>"), lista.index(">Orçamentos</span>"))
        self.assertLess(lista.index(">Orçamentos</span>"), lista.index(">Importação</span>"))
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', lista)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', edicao)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', clonagem)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', clonagem_periodo)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', importacao_despesas)
