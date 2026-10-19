from datetime import date
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from financeiro.models import EventoFinanceiro, NaturezaEvento


class RemoverObservacoesAutomaticasImportacaoMigrationTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="migration-observacao", password="senha")

    def criar_evento(self, observacao):
        return EventoFinanceiro.objects.create(
            usuario=self.usuario,
            natureza=NaturezaEvento.DESPESA,
            descricao="Evento importado",
            data=date(2026, 10, 1),
            valor=Decimal("10.00"),
            observacao=observacao,
        )

    def test_limpa_texto_automatico_e_preserva_observacao_revisada(self):
        somente_automatico = self.criar_evento("Importado do lote #15.")
        com_revisao = self.criar_evento("Conferido pelo usuário.\r\n\r\nImportado do lote #16.")
        preservado = self.criar_evento("Observação sem marcador de importação.")
        migration = import_module("financeiro.migrations.0014_remover_observacoes_automaticas_importacao")

        migration.remover_observacoes_automaticas(
            apps,
            SimpleNamespace(connection=connection),
        )

        somente_automatico.refresh_from_db()
        com_revisao.refresh_from_db()
        preservado.refresh_from_db()
        self.assertEqual(somente_automatico.observacao, "")
        self.assertEqual(com_revisao.observacao, "Conferido pelo usuário.")
        self.assertEqual(preservado.observacao, "Observação sem marcador de importação.")
