from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
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

    def test_menu_fica_entre_parcelas_e_importacao_e_permanece_ativo(self):
        orcamento = self.criar_orcamento()
        lista = self.client.get(reverse("orcamentos")).content.decode()
        edicao = self.client.get(reverse("orcamento_editar", args=[orcamento.pk])).content.decode()
        clonagem = self.client.get(reverse("orcamento_clonar", args=[orcamento.pk])).content.decode()

        self.assertLess(lista.index(">Parcelas futuras</span>"), lista.index(">Orçamentos</span>"))
        self.assertLess(lista.index(">Orçamentos</span>"), lista.index(">Importação</span>"))
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', lista)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', edicao)
        self.assertIn('href="/orcamentos/" class="active" aria-current="page"', clonagem)
