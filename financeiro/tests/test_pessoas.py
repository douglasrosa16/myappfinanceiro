from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Ambito, Conta, EventoFinanceiro, NaturezaEvento, Pessoa, Situacao


class PessoaCadastroTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.usuario = user_model.objects.create_user(username="titular-pessoas", password="senha")
        self.outro_usuario = user_model.objects.create_user(username="outro-pessoas", password="senha")
        self.client.force_login(self.usuario)
        self.pessoa = Pessoa.objects.create(
            usuario=self.usuario,
            nome="Fornecedor ativo",
            documento="123456789",
            observacao="Contato principal",
        )
        self.pessoa_inativa = Pessoa.objects.create(
            usuario=self.usuario,
            nome="Fornecedor inativo",
            ativa=False,
        )
        self.pessoa_alheia = Pessoa.objects.create(usuario=self.outro_usuario, nome="Pessoa de outro usuário")

    def test_listagem_segue_o_padrao_dos_cadastros(self):
        resposta = self.client.get(reverse("pessoas"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Pessoas")
        self.assertContains(resposta, "Nova pessoa")
        self.assertContains(resposta, self.pessoa.nome)
        self.assertContains(resposta, self.pessoa.documento)
        self.assertContains(resposta, self.pessoa.observacao)
        self.assertNotContains(resposta, self.pessoa_alheia.nome)

    def test_busca_e_filtro_de_situacao_respeitam_o_usuario(self):
        resposta_busca = self.client.get(reverse("pessoas"), {"q": "ativo"})
        resposta_ativas = self.client.get(reverse("pessoas"), {"status": "active"})
        resposta_inativas = self.client.get(reverse("pessoas"), {"status": "inactive"})

        self.assertContains(resposta_busca, self.pessoa.nome)
        self.assertContains(resposta_busca, self.pessoa_inativa.nome)
        self.assertNotContains(resposta_busca, self.pessoa_alheia.nome)
        self.assertContains(resposta_ativas, self.pessoa.nome)
        self.assertNotContains(resposta_ativas, self.pessoa_inativa.nome)
        self.assertContains(resposta_inativas, self.pessoa_inativa.nome)
        self.assertNotContains(resposta_inativas, self.pessoa.nome)

    def test_inclusao_e_edicao_atribuem_o_usuario_autenticado(self):
        resposta_criacao = self.client.post(
            reverse("pessoa_nova"),
            {"nome": "Nova pessoa", "documento": "987654321", "observacao": "Nova observação", "ativa": "on"},
        )
        criada = Pessoa.objects.get(nome="Nova pessoa")

        self.assertRedirects(resposta_criacao, reverse("pessoas"))
        self.assertEqual(criada.usuario, self.usuario)

        resposta_edicao = self.client.post(
            reverse("pessoa_editar", args=[criada.pk]),
            {"nome": "Pessoa atualizada", "documento": "987654321", "observacao": "Atualizada", "ativa": "on"},
        )
        criada.refresh_from_db()

        self.assertRedirects(resposta_edicao, reverse("pessoas"))
        self.assertEqual(criada.nome, "Pessoa atualizada")
        self.assertEqual(criada.observacao, "Atualizada")

    def test_nao_permite_editar_pessoa_de_outro_usuario(self):
        resposta = self.client.get(reverse("pessoa_editar", args=[self.pessoa_alheia.pk]))

        self.assertEqual(resposta.status_code, 404)

    def test_ativacao_inativacao_e_exclusao_sem_vinculos(self):
        resposta_inativar = self.client.post(reverse("cadastro_alternar", args=["pessoa", self.pessoa.pk]))
        self.pessoa.refresh_from_db()

        self.assertRedirects(resposta_inativar, reverse("pessoas"))
        self.assertFalse(self.pessoa.ativa)

        resposta_ativar = self.client.post(reverse("cadastro_alternar", args=["pessoa", self.pessoa.pk]))
        self.pessoa.refresh_from_db()

        self.assertRedirects(resposta_ativar, reverse("pessoas"))
        self.assertTrue(self.pessoa.ativa)

        pessoa_sem_vinculos = Pessoa.objects.create(usuario=self.usuario, nome="Pessoa descartável")
        resposta_excluir = self.client.post(reverse("cadastro_excluir", args=["pessoa", pessoa_sem_vinculos.pk]))

        self.assertRedirects(resposta_excluir, reverse("pessoas"))
        self.assertFalse(Pessoa.objects.filter(pk=pessoa_sem_vinculos.pk).exists())

    def test_exclusao_vinculada_e_protegida_e_historico_preservado(self):
        EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=NaturezaEvento.DESPESA,
            descricao="Serviço contratado",
            data=date(2026, 10, 6),
            valor=Decimal("100.00"),
            pessoa=self.pessoa,
            ambito=Ambito.PROFISSIONAL,
            situacao=Situacao.REALIZADO,
        )

        resposta = self.client.post(reverse("cadastro_excluir", args=["pessoa", self.pessoa.pk]), follow=True)

        self.assertTrue(Pessoa.objects.filter(pk=self.pessoa.pk).exists())
        self.assertContains(resposta, "Há vínculos com este cadastro. Use Inativar para preservar o histórico.")

    def test_novo_lancamento_exibe_somente_pessoas_ativas_do_usuario(self):
        resposta = self.client.get(reverse("evento_novo"))

        self.assertContains(resposta, self.pessoa.nome)
        self.assertNotContains(resposta, self.pessoa_inativa.nome)
        self.assertNotContains(resposta, self.pessoa_alheia.nome)

    def test_novo_lancamento_associa_pessoa_sem_alterar_nomes_livres_historicos(self):
        conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        historico = EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=NaturezaEvento.DESPESA,
            descricao="Histórico anterior",
            data=date(2026, 9, 1),
            valor=Decimal("25.00"),
            pessoa_nome_livre=self.pessoa.nome,
            ambito=Ambito.NAO_DEFINIDO,
            situacao=Situacao.REALIZADO,
        )

        resposta = self.client.post(
            reverse("evento_novo") + "?return_to=eventos&period=2026-10",
            {
                "descricao": "Novo lançamento associado",
                "natureza": NaturezaEvento.DESPESA,
                "data": "2026-10-06",
                "valor": "50,00",
                "origem": "CONTA",
                "conta": conta.pk,
                "cartao": "",
                "categoria": "",
                "pessoa": self.pessoa.pk,
                "pessoa_nome_livre": self.pessoa.nome,
                "ambito": Ambito.NAO_DEFINIDO,
                "situacao": Situacao.REALIZADO,
                "vencimento": "",
                "ciclo": "",
                "quantidade_parcelas": "1",
            },
        )
        novo = EventoFinanceiro.objects.get(descricao="Novo lançamento associado")
        historico.refresh_from_db()

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(novo.pessoa, self.pessoa)
        self.assertEqual(novo.pessoa_nome_livre, "")
        self.assertIsNone(historico.pessoa)
        self.assertEqual(historico.pessoa_nome_livre, self.pessoa.nome)
