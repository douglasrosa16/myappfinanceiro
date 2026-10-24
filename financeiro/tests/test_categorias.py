from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.forms import CategoriaForm
from financeiro.models import Categoria, EventoFinanceiro, RateioCategoria, Situacao


class CategoriaModelTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="categorias", password="senha")

    def test_defaults_de_classificacao(self):
        categoria = Categoria.objects.create(usuario=self.usuario, nome="Mercado")

        self.assertEqual(categoria.natureza, Categoria.Natureza.PESSOAL)
        self.assertEqual(categoria.essencialidade, Categoria.Essencialidade.NECESSARIO_VARIAVEL)
        self.assertTrue(categoria.computa_resultado)

    def test_rotulo_com_pai_nao_altera_nome_padrao_da_categoria(self):
        pai = Categoria.objects.create(usuario=self.usuario, nome="Receitas")
        filha = Categoria.objects.create(
            usuario=self.usuario,
            nome="Prestação de serviços",
            categoria_pai=pai,
        )

        self.assertEqual(pai.rotulo_com_pai, "Receitas")
        self.assertEqual(filha.rotulo_com_pai, "Prestação de serviços (Receitas)")
        self.assertEqual(str(filha), "Prestação de serviços")

    def test_rejeita_autorrelacionamento_e_ciclo_indireto(self):
        raiz = Categoria.objects.create(usuario=self.usuario, nome="Raiz")
        filha = Categoria.objects.create(usuario=self.usuario, nome="Filha", categoria_pai=raiz)
        neta = Categoria.objects.create(usuario=self.usuario, nome="Neta", categoria_pai=filha)

        raiz.categoria_pai = raiz
        with self.assertRaises(ValidationError):
            raiz.full_clean()

        raiz.categoria_pai = neta
        with self.assertRaises(ValidationError):
            raiz.full_clean()

    def test_rejeita_categoria_superior_de_outro_usuario(self):
        outro = get_user_model().objects.create_user(username="outro-categorias", password="senha")
        pai_alheio = Categoria.objects.create(usuario=outro, nome="Alheia")
        categoria = Categoria(usuario=self.usuario, nome="Local", categoria_pai=pai_alheio)

        with self.assertRaises(ValidationError):
            categoria.full_clean()

    def test_migracao_converte_ambos_e_categorias_neutras(self):
        antiga = Categoria.objects.create(usuario=self.usuario, nome="Categoria antiga")
        pagamento = Categoria.objects.create(usuario=self.usuario, nome="PAGAMENTO DE FÁTURA")
        transferencia = Categoria.objects.create(usuario=self.usuario, nome="Transferência entre contas próprias")
        Categoria.objects.filter(pk=antiga.pk).update(tipo="AMBOS")
        migracao = import_module("financeiro.migrations.0010_categoria_classificacao_resultado")

        migracao.migrar_categorias(apps, None)

        antiga.refresh_from_db()
        pagamento.refresh_from_db()
        transferencia.refresh_from_db()
        self.assertEqual(antiga.tipo, Categoria.Tipo.DESPESA)
        for categoria in (pagamento, transferencia):
            self.assertEqual(categoria.tipo, Categoria.Tipo.TRANSFERENCIA)
            self.assertEqual(categoria.essencialidade, Categoria.Essencialidade.NEUTRO)
            self.assertFalse(categoria.computa_resultado)


class CategoriaFormTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="form-categorias", password="senha")

    def test_persiste_classificacao_informada(self):
        form = CategoriaForm(
            data={
                "nome": "AWS",
                "tipo": Categoria.Tipo.DESPESA,
                "categoria_pai": "",
                "natureza": Categoria.Natureza.EMPRESARIAL,
                "essencialidade": Categoria.Essencialidade.PROFISSIONAL,
                "computa_resultado": "on",
                "ativa": "on",
            },
            usuario=self.usuario,
        )

        self.assertTrue(form.is_valid(), form.errors)
        categoria = form.save()
        self.assertEqual(categoria.natureza, Categoria.Natureza.EMPRESARIAL)
        self.assertEqual(categoria.essencialidade, Categoria.Essencialidade.PROFISSIONAL)
        self.assertTrue(categoria.computa_resultado)

    def test_exibe_rotulo_compoe_no_resultado(self):
        form = CategoriaForm(usuario=self.usuario)

        self.assertEqual(form.fields["computa_resultado"].label, "Compõe no resultado")

    def test_nao_oferece_propria_categoria_nem_descendentes_como_pai(self):
        raiz = Categoria.objects.create(usuario=self.usuario, nome="Raiz")
        filha = Categoria.objects.create(usuario=self.usuario, nome="Filha", categoria_pai=raiz)

        form = CategoriaForm(instance=raiz, usuario=self.usuario)

        self.assertNotIn(raiz, form.fields["categoria_pai"].queryset)
        self.assertNotIn(filha, form.fields["categoria_pai"].queryset)


class CategoriaViewsTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="views-categorias", password="senha")
        self.client.force_login(self.usuario)

    def test_listagem_exibe_novas_classificacoes(self):
        Categoria.objects.create(usuario=self.usuario, nome="Salário")
        Categoria.objects.create(
            usuario=self.usuario,
            nome="Restaurantes",
            natureza=Categoria.Natureza.PESSOAL,
            essencialidade=Categoria.Essencialidade.ESTILO_VIDA,
            computa_resultado=False,
        )

        resposta = self.client.get(reverse("categorias"))

        self.assertContains(resposta, "Natureza")
        self.assertContains(resposta, "Estilo de vida")
        self.assertContains(resposta, "Compõe")
        self.assertContains(resposta, "Não compõe")

    def test_exclusao_sem_vinculo_e_bloqueio_com_movimentacao(self):
        livre = Categoria.objects.create(usuario=self.usuario, nome="Livre")
        vinculada = Categoria.objects.create(usuario=self.usuario, nome="Vinculada")
        evento = EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza="DESPESA",
            descricao="Movimento",
            data="2026-10-06",
            valor="10.00",
            situacao=Situacao.REALIZADO,
        )
        RateioCategoria.objects.create(evento=evento, categoria=vinculada, valor="10.00")

        self.client.post(reverse("cadastro_excluir", args=["categoria", livre.pk]))
        resposta = self.client.post(
            reverse("cadastro_excluir", args=["categoria", vinculada.pk]),
            follow=True,
        )

        self.assertFalse(Categoria.objects.filter(pk=livre.pk).exists())
        self.assertTrue(Categoria.objects.filter(pk=vinculada.pk).exists())
        self.assertContains(resposta, "A categoria possui movimentações ou categorias vinculadas e deve ser inativada.")
