from importlib import import_module
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from financeiro.models import (
    Ambito,
    Cartao,
    Categoria,
    Conta,
    EventoFinanceiro,
    Importacao,
    ItemImportacao,
    NaturezaEvento,
    Pessoa,
    RegraCategoria,
    RegraCategoriaCondicao,
    Situacao,
)
from financeiro.services.importacao_ofx import aplicar_sugestao_classificacao, preparar_contexto_classificacao
from financeiro.services.regras_categoria import (
    DadosClassificacao,
    aplicar_resultados_regra,
    condicao_corresponde,
    carregar_regras_categoria,
    melhor_regra_manual,
    pontuar_regra_manual,
    primeira_regra_correspondente,
    regra_nova_corresponde,
)


class RegraCategoriaCadastroTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="regras", password="senha")
        self.outro_usuario = get_user_model().objects.create_user(username="regras-outro", password="senha")
        self.client.force_login(self.usuario)
        self.categoria = Categoria.objects.create(usuario=self.usuario, nome="Transporte")
        self.pessoa = Pessoa.objects.create(usuario=self.usuario, nome="Motorista")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta principal")
        self.cartao = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão principal",
            dia_vencimento=10,
        )
        self.categoria_outro = Categoria.objects.create(usuario=self.outro_usuario, nome="Categoria externa")
        self.conta_outro = Conta.objects.create(usuario=self.outro_usuario, nome="Conta externa")

    def dados_regra(self, **alteracoes):
        dados = {
            "nome": "Aplicativos de transporte",
            "prioridade": "10",
            "combinador": RegraCategoria.Combinador.TODAS,
            "categoria": str(self.categoria.pk),
            "ambito": Ambito.PESSOAL,
            "pessoa": "",
            "natureza_sugerida": "",
            "ativa": "on",
            "condicoes-TOTAL_FORMS": "1",
            "condicoes-INITIAL_FORMS": "0",
            "condicoes-MIN_NUM_FORMS": "1",
            "condicoes-MAX_NUM_FORMS": "20",
            "condicoes-0-ordem": "1",
            "condicoes-0-campo": RegraCategoriaCondicao.Campo.DESCRICAO,
            "condicoes-0-operador": RegraCategoriaCondicao.Operador.CONTEM,
            "condicoes-0-valor_texto": "UBER",
            "condicoes-0-valor_natureza": "",
            "condicoes-0-valor_origem": "",
            "condicoes-0-valor_conta": "",
            "condicoes-0-valor_cartao": "",
        }
        dados.update(alteracoes)
        return dados

    def criar_legada(self, texto="UBER"):
        regra = RegraCategoria.objects.create(
            usuario=self.usuario,
            texto=texto,
            nome="Transporte legado",
            prioridade=100,
            combinador=RegraCategoria.Combinador.TODAS,
            versao_motor=RegraCategoria.VersaoMotor.LEGADO,
            categoria=self.categoria,
            ambito=Ambito.PESSOAL,
            ativa=True,
        )
        RegraCategoriaCondicao.objects.create(
            regra=regra,
            ordem=1,
            campo=RegraCategoriaCondicao.Campo.DESCRICAO,
            operador=RegraCategoriaCondicao.Operador.CONTEM,
            valor=texto,
        )
        return regra

    def test_cria_regra_nova_persistida_sem_executa_la(self):
        resposta = self.client.post(reverse("regra_categoria_nova"), self.dados_regra())

        self.assertRedirects(resposta, reverse("regras_categoria"))
        regra = RegraCategoria.objects.get()
        self.assertEqual(regra.versao_motor, RegraCategoria.VersaoMotor.NOVO)
        self.assertEqual(regra.texto, "")
        self.assertTrue(regra.ativa)
        self.assertEqual(regra.condicoes.get().valor, "UBER")

    def test_exige_condicao_e_pelo_menos_um_resultado(self):
        sem_resultado = self.dados_regra(categoria="", ambito="")
        resposta = self.client.post(reverse("regra_categoria_nova"), sem_resultado)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe ao menos um resultado sugerido")
        self.assertFalse(RegraCategoria.objects.exists())

        sem_condicao = self.dados_regra(
            **{
                "condicoes-0-DELETE": "on",
                "condicoes-0-campo": "",
                "condicoes-0-operador": "",
                "condicoes-0-valor_texto": "",
            }
        )
        resposta = self.client.post(reverse("regra_categoria_nova"), sem_condicao)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["formset"].non_form_errors())
        self.assertFalse(RegraCategoria.objects.exists())

    def test_rejeita_operador_incompativel_e_normaliza_valor_absoluto(self):
        invalida = self.dados_regra(
            **{
                "condicoes-0-campo": RegraCategoriaCondicao.Campo.VALOR,
                "condicoes-0-operador": RegraCategoriaCondicao.Operador.CONTEM,
                "condicoes-0-valor_texto": "10,00",
            }
        )
        resposta = self.client.post(reverse("regra_categoria_nova"), invalida)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O operador não é compatível")

        valida = self.dados_regra(
            **{
                "condicoes-0-campo": RegraCategoriaCondicao.Campo.VALOR,
                "condicoes-0-operador": RegraCategoriaCondicao.Operador.MAIOR_IGUAL,
                "condicoes-0-valor_texto": "-1.234,56",
            }
        )
        resposta = self.client.post(reverse("regra_categoria_nova"), valida)
        self.assertRedirects(resposta, reverse("regras_categoria"))
        self.assertEqual(RegraCategoriaCondicao.objects.get().valor, "1234.56")

    def test_bloqueia_resultados_e_referencias_de_outro_usuario(self):
        resposta = self.client.post(
            reverse("regra_categoria_nova"),
            self.dados_regra(categoria=str(self.categoria_outro.pk)),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Faça uma escolha válida")
        self.assertFalse(RegraCategoria.objects.exists())

        resposta = self.client.post(
            reverse("regra_categoria_nova"),
            self.dados_regra(
                **{
                    "condicoes-0-campo": RegraCategoriaCondicao.Campo.CONTA,
                    "condicoes-0-operador": RegraCategoriaCondicao.Operador.IGUAL,
                    "condicoes-0-valor_texto": "",
                    "condicoes-0-valor_conta": str(self.conta_outro.pk),
                }
            ),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Faça uma escolha válida")
        self.assertFalse(RegraCategoria.objects.exists())

    def test_edicao_compativel_preserva_legado_e_sincroniza_texto(self):
        regra = self.criar_legada()
        condicao = regra.condicoes.get()
        dados = self.dados_regra(
            nome="Transporte por aplicativo",
            **{
                "condicoes-INITIAL_FORMS": "1",
                "condicoes-0-id": str(condicao.pk),
                "condicoes-0-valor_texto": "99 ",
            },
        )

        resposta = self.client.post(reverse("regra_categoria_editar", args=[regra.pk]), dados)

        self.assertRedirects(resposta, reverse("regras_categoria"))
        regra.refresh_from_db()
        self.assertEqual(regra.versao_motor, RegraCategoria.VersaoMotor.LEGADO)
        self.assertEqual(regra.texto, "99")
        self.assertEqual(regra.condicoes.get().valor, "99")

    def test_recurso_incompativel_promove_legada_para_nova(self):
        regra = self.criar_legada()
        condicao = regra.condicoes.get()
        dados = self.dados_regra(
            combinador=RegraCategoria.Combinador.QUALQUER,
            natureza_sugerida=NaturezaEvento.DESPESA,
            **{
                "condicoes-TOTAL_FORMS": "2",
                "condicoes-INITIAL_FORMS": "1",
                "condicoes-0-id": str(condicao.pk),
                "condicoes-1-ordem": "2",
                "condicoes-1-campo": RegraCategoriaCondicao.Campo.OBSERVACAO,
                "condicoes-1-operador": RegraCategoriaCondicao.Operador.NAO_CONTEM,
                "condicoes-1-valor_texto": "reembolso",
                "condicoes-1-valor_natureza": "",
                "condicoes-1-valor_origem": "",
                "condicoes-1-valor_conta": "",
                "condicoes-1-valor_cartao": "",
            },
        )

        resposta = self.client.post(reverse("regra_categoria_editar", args=[regra.pk]), dados, follow=True)

        self.assertEqual(resposta.status_code, 200)
        regra.refresh_from_db()
        self.assertEqual(regra.versao_motor, RegraCategoria.VersaoMotor.NOVO)
        self.assertEqual(regra.condicoes.count(), 2)
        self.assertContains(resposta, "promovida para o novo formato")

    def test_reordena_condicoes_sem_violar_posicao_unica(self):
        regra = self.criar_legada()
        primeira = regra.condicoes.get()
        segunda = RegraCategoriaCondicao.objects.create(
            regra=regra,
            ordem=2,
            campo=RegraCategoriaCondicao.Campo.OBSERVACAO,
            operador=RegraCategoriaCondicao.Operador.CONTEM,
            valor="corrida",
        )
        dados = self.dados_regra(
            **{
                "condicoes-TOTAL_FORMS": "2",
                "condicoes-INITIAL_FORMS": "2",
                "condicoes-0-id": str(primeira.pk),
                "condicoes-0-ordem": "2",
                "condicoes-1-id": str(segunda.pk),
                "condicoes-1-ordem": "1",
                "condicoes-1-campo": RegraCategoriaCondicao.Campo.OBSERVACAO,
                "condicoes-1-operador": RegraCategoriaCondicao.Operador.CONTEM,
                "condicoes-1-valor_texto": "corrida",
                "condicoes-1-valor_natureza": "",
                "condicoes-1-valor_origem": "",
                "condicoes-1-valor_conta": "",
                "condicoes-1-valor_cartao": "",
            }
        )

        resposta = self.client.post(reverse("regra_categoria_editar", args=[regra.pk]), dados)

        self.assertRedirects(resposta, reverse("regras_categoria"))
        self.assertEqual(list(regra.condicoes.order_by("ordem").values_list("pk", flat=True)), [segunda.pk, primeira.pk])

    def test_duplica_como_nova_sem_alterar_original(self):
        original = self.criar_legada()

        resposta = self.client.post(reverse("regra_categoria_duplicar", args=[original.pk]))

        self.assertRedirects(resposta, reverse("regras_categoria"))
        original.refresh_from_db()
        copia = RegraCategoria.objects.exclude(pk=original.pk).get()
        self.assertEqual(original.versao_motor, RegraCategoria.VersaoMotor.LEGADO)
        self.assertEqual(copia.versao_motor, RegraCategoria.VersaoMotor.NOVO)
        self.assertEqual(copia.condicoes.get().valor, original.condicoes.get().valor)

    def test_ativacao_exige_post_e_respeita_usuario(self):
        regra = self.criar_legada()
        self.assertEqual(self.client.get(reverse("regra_categoria_alternar", args=[regra.pk])).status_code, 405)

        resposta = self.client.post(reverse("regra_categoria_alternar", args=[regra.pk]))
        self.assertRedirects(resposta, reverse("regras_categoria"))
        regra.refresh_from_db()
        self.assertFalse(regra.ativa)

        regra_outro = RegraCategoria.objects.create(
            usuario=self.outro_usuario,
            nome="Regra externa",
            categoria=self.categoria_outro,
        )
        self.assertEqual(
            self.client.post(reverse("regra_categoria_alternar", args=[regra_outro.pk])).status_code,
            404,
        )

    def test_listagem_editor_e_menu_expoem_estado_da_fase_dois(self):
        self.criar_legada()
        RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Regra nova",
            categoria=self.categoria,
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
        )
        resposta = self.client.get(reverse("regras_categoria"))
        self.assertContains(resposta, "Legada — compatibilidade")
        self.assertContains(resposta, "<h1>Regras</h1>", html=False)
        self.assertContains(resposta, '<details class="nav-group active" open>', html=False)
        self.assertContains(resposta, "Nova — em uso")
        self.assertContains(resposta, "data-modal-url")

        editor = self.client.get(reverse("regra_categoria_nova"))
        self.assertContains(editor, "data-regra-categoria-form")
        self.assertContains(editor, "data-condition-template")
        self.assertContains(editor, "rule-name-field")
        self.assertContains(editor, "rule-settings")
        self.assertContains(editor, "rule-results-grid")
        self.assertNotContains(editor, "A integração com lançamentos manuais ficará para uma fase posterior.")

    def test_nova_regra_recebe_proxima_prioridade_do_usuario(self):
        inicial = self.client.get(reverse("regra_categoria_nova"))
        self.assertContains(inicial, 'name="prioridade" value="1"', html=False)

        RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Primeira",
            prioridade=1,
            categoria=self.categoria,
        )
        RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Terceira",
            prioridade=3,
            categoria=self.categoria,
        )
        RegraCategoria.objects.create(
            usuario=self.outro_usuario,
            nome="Prioridade externa",
            prioridade=99,
            categoria=self.categoria_outro,
        )

        proxima = self.client.get(reverse("regra_categoria_nova"))

        self.assertContains(proxima, 'name="prioridade" value="4"', html=False)


class RegraCategoriaCompatibilidadeImportacaoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="importador-regras", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta importação")
        self.categoria_legada = Categoria.objects.create(usuario=self.usuario, nome="Legada")
        self.categoria_nova = Categoria.objects.create(usuario=self.usuario, nome="Nova")
        self.importacao = Importacao.objects.create(
            usuario=self.usuario,
            arquivo="importacoes/testes/regras.ofx",
            nome_arquivo="regras.ofx",
            hash_arquivo="b" * 64,
            origem=Importacao.Origem.CONTA,
            conta=self.conta,
            status=Importacao.Status.EM_REVISAO,
        )

    def _condicao_descricao(self, regra, valor="UBER", operador=RegraCategoriaCondicao.Operador.CONTEM):
        return RegraCategoriaCondicao.objects.create(
            regra=regra,
            ordem=1,
            campo=RegraCategoriaCondicao.Campo.DESCRICAO,
            operador=operador,
            valor=valor,
        )

    def _item(self, descricao="Pagamento UBER viagem"):
        return ItemImportacao(
            importacao=self.importacao,
            descricao_original=descricao,
            valor=Decimal("25.00"),
            natureza=NaturezaEvento.DESPESA,
            ambito=Ambito.NAO_DEFINIDO,
            status=ItemImportacao.Status.NOVO,
            acao=ItemImportacao.Acao.CRIAR,
        )

    def test_importador_prioriza_regra_nova_sobre_legada(self):
        nova = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Nova prioritária",
            prioridade=1,
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
            categoria=self.categoria_nova,
            ativa=True,
        )
        self._condicao_descricao(nova)
        legada = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Legada em uso",
            prioridade=999,
            texto="UBER",
            versao_motor=RegraCategoria.VersaoMotor.LEGADO,
            categoria=self.categoria_legada,
            ativa=True,
        )
        item = self._item()

        contexto = preparar_contexto_classificacao(self.importacao, [item])
        aplicar_sugestao_classificacao(item, contexto)

        self.assertEqual(contexto["regras"], [legada])
        self.assertEqual(item.categoria, self.categoria_nova)
        self.assertIn("Nova prioritária", item.motivo_status)

    def test_legado_e_usado_somente_quando_nenhuma_nova_corresponde(self):
        nova = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Somente nova",
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
            categoria=self.categoria_nova,
            ativa=True,
        )
        self._condicao_descricao(nova, valor="NETFLIX")
        RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Legada em uso",
            texto="UBER",
            versao_motor=RegraCategoria.VersaoMotor.LEGADO,
            categoria=self.categoria_legada,
            ativa=True,
        )
        item = self._item()

        aplicar_sugestao_classificacao(item, preparar_contexto_classificacao(self.importacao, [item]))

        self.assertEqual(item.categoria, self.categoria_legada)
        self.assertIn("regra legada", item.motivo_status)

    def test_correspondencia_nova_bloqueia_legado_mesmo_sem_categoria(self):
        pessoa = Pessoa.objects.create(usuario=self.usuario, nome="Passageiro")
        nova = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Nova somente pessoa",
            prioridade=1,
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
            pessoa=pessoa,
            ativa=True,
        )
        self._condicao_descricao(nova)
        RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Legada com categoria",
            texto="UBER",
            versao_motor=RegraCategoria.VersaoMotor.LEGADO,
            categoria=self.categoria_legada,
            ativa=True,
        )
        item = self._item()

        aplicar_sugestao_classificacao(item, preparar_contexto_classificacao(self.importacao, [item]))

        self.assertEqual(item.pessoa, pessoa)
        self.assertIsNone(item.categoria)


class AvaliadorRegraCategoriaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="avaliador-regras", password="senha")
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta avaliador")
        self.cartao = Cartao.objects.create(
            usuario=self.usuario,
            nome="Cartão avaliador",
            dia_vencimento=10,
        )
        self.dados = DadosClassificacao(
            descricao="Café   Central Premium!",
            observacao="Cliente VIP",
            valor=Decimal("125.50"),
            natureza=NaturezaEvento.DESPESA,
            origem=Importacao.Origem.CONTA,
            conta_id=self.conta.pk,
            cartao_id=self.cartao.pk,
        )

    def test_todos_os_campos_e_operadores_sao_avaliados(self):
        casos = (
            ("descricao contém", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "cafe central"),
            ("descrição não contém", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.NAO_CONTEM, "posto"),
            ("descrição igual", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.IGUAL, "cafe central premium"),
            ("descrição diferente", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.DIFERENTE, "outro"),
            ("descrição começa", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.COMECA_COM, "café central"),
            ("descrição termina", RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.TERMINA_COM, "premium"),
            ("observação", RegraCategoriaCondicao.Campo.OBSERVACAO, RegraCategoriaCondicao.Operador.CONTEM, "cliente vip"),
            ("valor igual", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.IGUAL, "125.50"),
            ("valor diferente", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.DIFERENTE, "10"),
            ("valor maior", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.MAIOR, "100"),
            ("valor maior igual", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.MAIOR_IGUAL, "125.50"),
            ("valor menor", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.MENOR, "200"),
            ("valor menor igual", RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.MENOR_IGUAL, "125.50"),
            ("natureza igual", RegraCategoriaCondicao.Campo.NATUREZA, RegraCategoriaCondicao.Operador.IGUAL, NaturezaEvento.DESPESA),
            ("natureza diferente", RegraCategoriaCondicao.Campo.NATUREZA, RegraCategoriaCondicao.Operador.DIFERENTE, NaturezaEvento.RECEITA),
            ("origem", RegraCategoriaCondicao.Campo.ORIGEM, RegraCategoriaCondicao.Operador.IGUAL, Importacao.Origem.CONTA),
            ("conta", RegraCategoriaCondicao.Campo.CONTA, RegraCategoriaCondicao.Operador.IGUAL, str(self.conta.pk)),
            ("cartão", RegraCategoriaCondicao.Campo.CARTAO, RegraCategoriaCondicao.Operador.IGUAL, str(self.cartao.pk)),
        )
        for nome, campo, operador, valor in casos:
            with self.subTest(nome=nome):
                condicao = SimpleNamespace(campo=campo, operador=operador, valor=valor)
                self.assertTrue(condicao_corresponde(condicao, self.dados))

    def test_combinadores_e_ordenacao_deterministica(self):
        categoria = Categoria.objects.create(usuario=self.usuario, nome="Cafeteria")
        regra_and = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="AND",
            prioridade=20,
            combinador=RegraCategoria.Combinador.TODAS,
            categoria=categoria,
        )
        regra_or = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="OR",
            prioridade=10,
            combinador=RegraCategoria.Combinador.QUALQUER,
            categoria=categoria,
        )
        for regra in (regra_and, regra_or):
            RegraCategoriaCondicao.objects.create(
                regra=regra,
                ordem=1,
                campo=RegraCategoriaCondicao.Campo.DESCRICAO,
                operador=RegraCategoriaCondicao.Operador.CONTEM,
                valor="CAFÉ",
            )
            RegraCategoriaCondicao.objects.create(
                regra=regra,
                ordem=2,
                campo=RegraCategoriaCondicao.Campo.OBSERVACAO,
                operador=RegraCategoriaCondicao.Operador.CONTEM,
                valor="INEXISTENTE",
            )

        self.assertFalse(regra_nova_corresponde(regra_and, self.dados))
        self.assertTrue(regra_nova_corresponde(regra_or, self.dados))
        conjunto = SimpleNamespace(novas=(regra_or, regra_and), legadas=())
        self.assertEqual(primeira_regra_correspondente(self.dados, conjunto), regra_or)

    def test_resultado_de_outro_usuario_nao_e_aplicado(self):
        outro = get_user_model().objects.create_user(username="resultado-externo", password="senha")
        categoria_externa = Categoria.objects.create(usuario=outro, nome="Externa")
        regra = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Regra inconsistente",
            categoria=categoria_externa,
        )
        importacao = Importacao.objects.create(
            usuario=self.usuario,
            arquivo="importacoes/testes/isolamento.ofx",
            nome_arquivo="isolamento.ofx",
            hash_arquivo="c" * 64,
            origem=Importacao.Origem.CONTA,
            conta=self.conta,
            status=Importacao.Status.EM_REVISAO,
        )
        item = ItemImportacao(importacao=importacao, natureza=NaturezaEvento.DESPESA)

        campos = aplicar_resultados_regra(item, regra)

        self.assertFalse(campos)
        self.assertIsNone(item.categoria)


class SugestaoRegraLancamentoManualTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="sugestao-manual", password="senha")
        self.outro = get_user_model().objects.create_user(username="sugestao-manual-outro", password="senha")
        self.client.force_login(self.usuario)
        self.conta = Conta.objects.create(usuario=self.usuario, nome="Conta manual")
        self.cartao = Cartao.objects.create(usuario=self.usuario, nome="Cartão manual", dia_vencimento=10)
        self.categoria = Categoria.objects.create(usuario=self.usuario, nome="Mercado")
        self.pessoa = Pessoa.objects.create(usuario=self.usuario, nome="Fornecedor")

    def criar_regra(self, nome, condicoes, **campos):
        regra = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome=nome,
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
            ativa=True,
            **campos,
        )
        for ordem, (campo, operador, valor) in enumerate(condicoes, start=1):
            RegraCategoriaCondicao.objects.create(
                regra=regra,
                ordem=ordem,
                campo=campo,
                operador=operador,
                valor=valor,
            )
        return regra

    def dados(self, **alteracoes):
        valores = {
            "descricao": "",
            "observacao": "",
            "valor": None,
            "natureza": NaturezaEvento.DESPESA,
            "origem": Importacao.Origem.CONTA,
            "conta_id": self.conta.pk,
            "cartao_id": None,
        }
        valores.update(alteracoes)
        return DadosClassificacao(**valores)

    def test_and_ignora_campos_ausentes_e_rejeita_condicao_contradita(self):
        regra = self.criar_regra(
            "Uber completo",
            (
                (RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "UBER"),
                (RegraCategoriaCondicao.Campo.VALOR, RegraCategoriaCondicao.Operador.IGUAL, "50"),
                (RegraCategoriaCondicao.Campo.OBSERVACAO, RegraCategoriaCondicao.Operador.NAO_CONTEM, "PESSOAL"),
            ),
            combinador=RegraCategoria.Combinador.TODAS,
        )

        self.assertEqual(pontuar_regra_manual(regra, self.dados(descricao="Uber")), 1)
        self.assertIsNone(pontuar_regra_manual(regra, self.dados(descricao="Uber", valor=Decimal("40"))))

    def test_or_aceita_uma_correspondencia_e_maior_pontuacao_vence_prioridade(self):
        simples = self.criar_regra(
            "Simples prioritária",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "MERCADO"),),
            prioridade=1,
        )
        especifica = self.criar_regra(
            "Específica",
            (
                (RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "MERCADO"),
                (RegraCategoriaCondicao.Campo.ORIGEM, RegraCategoriaCondicao.Operador.IGUAL, Importacao.Origem.CONTA),
                (RegraCategoriaCondicao.Campo.OBSERVACAO, RegraCategoriaCondicao.Operador.CONTEM, "INEXISTENTE"),
            ),
            combinador=RegraCategoria.Combinador.QUALQUER,
            prioridade=50,
        )

        resultado = melhor_regra_manual(
            self.dados(descricao="Mercado Central", observacao="Compra semanal"),
            carregar_regras_categoria(self.usuario),
        )

        self.assertNotEqual(resultado.regra, simples)
        self.assertEqual(resultado.regra, especifica)
        self.assertEqual(resultado.condicoes_correspondentes, 2)

    def test_prioridade_e_id_desempatam_mesma_pontuacao(self):
        posterior = self.criar_regra(
            "Prioridade posterior",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "CAFÉ"),),
            prioridade=20,
        )
        vencedora = self.criar_regra(
            "Prioridade vencedora",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "CAFÉ"),),
            prioridade=10,
        )
        mesmo_empate_id_maior = self.criar_regra(
            "Mesmo empate",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "CAFÉ"),),
            prioridade=10,
        )

        resultado = melhor_regra_manual(self.dados(descricao="Café"), carregar_regras_categoria(self.usuario))

        self.assertNotEqual(resultado.regra, posterior)
        self.assertNotEqual(resultado.regra, mesmo_empate_id_maior)
        self.assertEqual(resultado.regra, vencedora)

    def test_fallback_legado_so_ocorre_sem_candidata_nova(self):
        self.criar_regra(
            "Nova sem correspondência",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "NETFLIX"),),
        )
        legada = RegraCategoria.objects.create(
            usuario=self.usuario,
            nome="Uber legada",
            texto="UBER",
            versao_motor=RegraCategoria.VersaoMotor.LEGADO,
            categoria=self.categoria,
            ativa=True,
        )

        resultado = melhor_regra_manual(self.dados(descricao="Viagem Uber"), carregar_regras_categoria(self.usuario))

        self.assertEqual(resultado.regra, legada)

    def test_endpoint_retorna_resultados_e_tolera_valor_parcial(self):
        regra = self.criar_regra(
            "Mercado completo",
            ((RegraCategoriaCondicao.Campo.DESCRICAO, RegraCategoriaCondicao.Operador.CONTEM, "MERCADO"),),
            categoria=self.categoria,
            pessoa=self.pessoa,
            ambito=Ambito.PESSOAL,
            natureza_sugerida=NaturezaEvento.DESPESA,
        )

        resposta = self.client.post(
            reverse("regra_categoria_sugerir_lancamento"),
            {
                "descricao": "Mercado Central",
                "observacao": "",
                "natureza": NaturezaEvento.DESPESA,
                "valor": "12,",
                "origem": Importacao.Origem.CONTA,
                "conta": self.conta.pk,
                "cartao": "",
                "data": "01/01/1999",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["encontrada"])
        self.assertEqual(dados["regra"], {"id": regra.pk, "nome": regra.nome, "versao": "NOVO"})
        self.assertEqual(dados["sugestoes"]["categoria"], {"id": self.categoria.pk, "rotulo": "Mercado"})
        self.assertEqual(dados["sugestoes"]["pessoa"], {"id": self.pessoa.pk, "rotulo": "Fornecedor"})
        self.assertEqual(dados["sugestoes"]["ambito"], Ambito.PESSOAL)
        self.assertEqual(dados["sugestoes"]["natureza"], NaturezaEvento.DESPESA)

    def test_endpoint_bloqueia_referencia_externa_e_natureza_excluida(self):
        conta_externa = Conta.objects.create(usuario=self.outro, nome="Conta externa")
        self.criar_regra(
            "Regra ampla",
            ((RegraCategoriaCondicao.Campo.NATUREZA, RegraCategoriaCondicao.Operador.IGUAL, NaturezaEvento.DESPESA),),
            categoria=self.categoria,
        )

        externa = self.client.post(
            reverse("regra_categoria_sugerir_lancamento"),
            {"natureza": NaturezaEvento.DESPESA, "origem": "CONTA", "conta": conta_externa.pk},
        )
        pagamento = self.client.post(
            reverse("regra_categoria_sugerir_lancamento"),
            {"natureza": NaturezaEvento.PAGAMENTO_FATURA, "origem": "CONTA", "conta": self.conta.pk},
        )

        self.assertEqual(externa.status_code, 400)
        self.assertIn("conta", externa.json()["erros"])
        self.assertEqual(pagamento.status_code, 200)
        self.assertFalse(pagamento.json()["encontrada"])

    def test_endpoint_exige_login_e_post(self):
        self.assertEqual(self.client.get(reverse("regra_categoria_sugerir_lancamento")).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("regra_categoria_sugerir_lancamento")).status_code, 302)

    def test_sugestao_aparece_somente_nos_formularios_de_criacao(self):
        evento = EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=NaturezaEvento.DESPESA,
            descricao="Lançamento para clonar",
            data=date(2026, 10, 20),
            valor=Decimal("10.00"),
            situacao=Situacao.REALIZADO,
        )

        novo = self.client.get(reverse("evento_novo"))
        compra = self.client.get(reverse("compra_cartao_nova"))
        clone = self.client.get(reverse("evento_novo"), {"clone_evento": evento.pk})
        atributo = f'data-regra-sugestao-url="{reverse("regra_categoria_sugerir_lancamento")}"'

        self.assertContains(novo, atributo)
        self.assertContains(novo, "data-regra-sugestao-status")
        self.assertContains(compra, atributo)
        self.assertNotContains(clone, atributo)


class RegraCategoriaMigrationTests(TestCase):
    def test_converte_regra_existente_sem_perder_resultados(self):
        usuario = get_user_model().objects.create_user(username="migration-regras", password="senha")
        categoria = Categoria.objects.create(usuario=usuario, nome="Assinaturas")
        pessoa = Pessoa.objects.create(usuario=usuario, nome="Fornecedor")
        regra = RegraCategoria.objects.create(
            usuario=usuario,
            texto="NETFLIX",
            nome="",
            versao_motor=RegraCategoria.VersaoMotor.NOVO,
            categoria=categoria,
            pessoa=pessoa,
            ambito=Ambito.PROFISSIONAL,
            ativa=False,
        )
        migration = import_module("financeiro.migrations.0017_regras_categoria_cadastro")

        migration.migrar_regras_categoria(apps, SimpleNamespace(connection=connection))

        regra.refresh_from_db()
        self.assertEqual(regra.nome, "NETFLIX")
        self.assertEqual(regra.versao_motor, RegraCategoria.VersaoMotor.LEGADO)
        self.assertEqual(regra.categoria, categoria)
        self.assertEqual(regra.pessoa, pessoa)
        self.assertEqual(regra.ambito, Ambito.PROFISSIONAL)
        self.assertFalse(regra.ativa)
        condicao = regra.condicoes.get()
        self.assertEqual(condicao.campo, RegraCategoriaCondicao.Campo.DESCRICAO)
        self.assertEqual(condicao.operador, RegraCategoriaCondicao.Operador.CONTEM)
        self.assertEqual(condicao.valor, "NETFLIX")
