from decimal import Decimal

from django.test import SimpleTestCase

from financeiro.templatetags.financeiro_format import classe_valor


class ClasseValorTests(SimpleTestCase):
    def test_classifica_valores_assinados(self):
        self.assertEqual(classe_valor(Decimal("10.00")), "amount-positive")
        self.assertEqual(classe_valor(Decimal("-10.00")), "amount-negative")

    def test_classifica_magnitude_de_saida(self):
        self.assertEqual(classe_valor(Decimal("10.00"), "saida"), "amount-negative")
        self.assertEqual(classe_valor(Decimal("-10.00"), "saida"), "amount-positive")
        self.assertEqual(classe_valor(Decimal("10.00"), "PAGAR"), "amount-negative")

    def test_mantem_zero_nulo_e_invalido_neutros(self):
        self.assertEqual(classe_valor(Decimal("0.00")), "")
        self.assertEqual(classe_valor(None), "")
        self.assertEqual(classe_valor("invalido"), "")
