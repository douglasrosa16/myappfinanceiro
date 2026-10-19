from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from financeiro.ofx import CartaoOFXAdapter, OFXError, OFXParser


OFX_CONTA = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII

<OFX><SIGNONMSGSRSV1><SONRS><FI><ORG>SICOOB<FID>756</FI></SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>756<ACCTID>12345</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20261001000000<DTEND>20261031235959
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005120000<TRNAMT>-125.50<FITID>A1<CHECKNUM>PIX<MEMO>Mercado Central</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261006120000<TRNAMT>2500.00<FITID>A2<MEMO>Cliente XPTO</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>2374.50<DTASOF>20261006120000</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""

OFX_CARTAO = """<?xml version="1.0" encoding="UTF-8"?>
<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CURDEF>BRL<CCACCTFROM><ACCTID>9999</CCACCTFROM>
<BANKTRANLIST><DTSTART>20261001<DTEND>20261031
<CCSTMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261010<TRNAMT>-100.00<FITID>C1<MEMO>LOJA TESTE 02/12</CCSTMTTRN>
</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>"""


class OFXParserTests(SimpleTestCase):
    def test_parse_conta_sgml_com_saldo_e_sinais(self):
        documento = OFXParser.parse(OFX_CONTA)
        self.assertEqual(documento.origem, "CONTA")
        self.assertEqual(documento.identificador_conta, "12345")
        self.assertEqual(documento.saldo, Decimal("2374.50"))
        self.assertEqual([item.valor for item in documento.transacoes], [Decimal("-125.50"), Decimal("2500.00")])

    def test_parse_cartao_xml_e_parcela(self):
        documento = OFXParser.parse(OFX_CARTAO)
        self.assertEqual(documento.origem, "CARTAO")
        self.assertEqual(CartaoOFXAdapter().installment(documento.transacoes[0].descricao), (2, 12))

    def test_ofxparse_tipo_numerico_e_estrutura_cc_identificam_cartao(self):
        transacao = SimpleNamespace(
            id="C1",
            date=datetime(2026, 10, 10),
            amount=Decimal("-100.00"),
            memo="COMPRA CARTAO",
            payee="",
            type="debit",
            checknum="",
        )
        statement = SimpleNamespace(
            transactions=[transacao],
            start_date=None,
            end_date=None,
            ledger_balance_date=None,
            balance=None,
            currency="BRL",
        )
        account = SimpleNamespace(
            type=2,
            statement=statement,
            routing_number="",
            account_id="9999",
        )
        parsed = SimpleNamespace(account=account, institution=None)
        documento = OFXParser._from_library(parsed, "<CREDITCARDMSGSRSV1><CCSTMTRS><CCACCTFROM>")
        self.assertEqual(documento.origem, "CARTAO")

    def test_rejeita_arquivo_sem_ofx(self):
        with self.assertRaises(OFXError):
            OFXParser.parse("arquivo inválido")
