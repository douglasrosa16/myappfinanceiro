from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
import re
import unicodedata
import warnings


class OFXError(ValueError):
    pass


@dataclass(frozen=True)
class OFXTransaction:
    identificador: str
    data: date | None
    valor: Decimal
    descricao: str
    tipo: str = ""
    documento: str = ""
    raw: dict | None = None


@dataclass(frozen=True)
class OFXDocument:
    origem: str
    instituicao: str
    banco: str
    identificador_conta: str
    data_inicio: date | None
    data_fim: date | None
    data_posicao: date | None
    saldo: Decimal | None
    moeda: str
    transacoes: list[OFXTransaction]


@dataclass(frozen=True)
class OFXPreviewItem:
    identificador: str
    data: str
    valor: Decimal
    descricao: str


class OFXParser:
    """Fachada tolerante a OFX 1.x (SGML) e 2.x (XML)."""

    @classmethod
    def parse(cls, conteudo: bytes | str) -> OFXDocument:
        texto = cls._decode(conteudo) if isinstance(conteudo, bytes) else conteudo
        if "<OFX" not in texto.upper():
            raise OFXError("O arquivo não contém uma estrutura OFX válida.")
        try:
            from ofxparse import OfxParser  # type: ignore
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = OfxParser.parse(StringIO(texto))
            return cls._from_library(parsed, texto)
        except Exception:
            return cls._parse_tolerant(texto)

    @staticmethod
    def _decode(conteudo: bytes) -> str:
        encodings = []
        header = conteudo[:500].decode("ascii", errors="ignore")
        match = re.search(r"ENCODING\s*:\s*([^\r\n]+)", header, flags=re.I)
        if match:
            declared = match.group(1).strip().upper()
            encodings.append({"USASCII": "ascii", "UNICODE": "utf-8", "UTF-8": "utf-8"}.get(declared, declared))
        encodings.extend(["utf-8-sig", "cp1252", "latin-1"])
        for encoding in encodings:
            try:
                return conteudo.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return conteudo.decode("latin-1", errors="replace")

    @classmethod
    def _from_library(cls, parsed, texto_original: str = "") -> OFXDocument:
        account = parsed.account
        statement = account.statement
        account_type = str(getattr(account, "type", "")).lower()
        estrutura_cartao = bool(re.search(r"<(CREDITCARDMSGSRSV1|CCSTMTRS|CCACCTFROM)\b", texto_original, flags=re.I))
        tipo_cartao_ofxparse = getattr(account, "type", None) == 2
        origem = (
            "CARTAO"
            if estrutura_cartao
            or tipo_cartao_ofxparse
            or "credit" in account_type
            or account.__class__.__name__.lower().startswith("credit")
            else "CONTA"
        )
        institution = getattr(parsed, "institution", None)
        instituicao = str(getattr(institution, "organization", "") or getattr(institution, "fid", "") or "")
        transacoes = []
        for transaction in statement.transactions:
            descricao = str(getattr(transaction, "memo", "") or getattr(transaction, "payee", "") or "Sem descrição").strip()
            data_transacao = getattr(transaction, "date", None)
            if isinstance(data_transacao, datetime):
                data_transacao = data_transacao.date()
            transacoes.append(
                OFXTransaction(
                    identificador=str(getattr(transaction, "id", "") or ""),
                    data=data_transacao,
                    valor=Decimal(str(getattr(transaction, "amount", "0"))),
                    descricao=descricao,
                    tipo=str(getattr(transaction, "type", "") or ""),
                    documento=str(getattr(transaction, "checknum", "") or ""),
                    raw={"parser": "ofxparse"},
                )
            )
        if not transacoes:
            raise OFXError("Nenhum lançamento foi encontrado no arquivo OFX.")
        return OFXDocument(
            origem=origem,
            instituicao=instituicao,
            banco=str(getattr(account, "routing_number", "") or ""),
            identificador_conta=str(getattr(account, "account_id", "") or ""),
            data_inicio=cls._as_date(getattr(statement, "start_date", None)),
            data_fim=cls._as_date(getattr(statement, "end_date", None)),
            data_posicao=cls._as_date(getattr(statement, "ledger_balance_date", None)),
            saldo=cls._as_decimal(getattr(statement, "balance", None)),
            moeda=str(getattr(statement, "currency", "") or ""),
            transacoes=transacoes,
        )

    @classmethod
    def _parse_tolerant(cls, texto: str) -> OFXDocument:
        origem = "CARTAO" if re.search(r"<(CCSTMTRS|CCACCTFROM|CCSTMTTRN)\b", texto, flags=re.I) else "CONTA"
        tag_transacao = "CCSTMTTRN" if origem == "CARTAO" and re.search(r"<CCSTMTTRN\b", texto, flags=re.I) else "STMTTRN"
        blocos = re.findall(
            rf"<{tag_transacao}\b[^>]*>(.*?)(?=</{tag_transacao}>|<{tag_transacao}\b|</(?:BANKTRANLIST|CCBANKTRANLIST)>|$)",
            texto,
            flags=re.I | re.S,
        )
        transacoes = []
        for bloco in blocos:
            valor_raw = cls._tag(bloco, "TRNAMT")
            if not valor_raw:
                continue
            try:
                valor = Decimal(valor_raw.replace(",", "."))
            except InvalidOperation as exc:
                raise OFXError(f"Valor OFX inválido: {valor_raw}") from exc
            descricao = cls._tag(bloco, "MEMO") or cls._tag(bloco, "NAME") or "Sem descrição"
            raw = {tag: cls._tag(bloco, tag) for tag in ("TRNTYPE", "DTPOSTED", "TRNAMT", "FITID", "CHECKNUM", "NAME", "MEMO")}
            transacoes.append(
                OFXTransaction(
                    identificador=cls._tag(bloco, "FITID"),
                    data=cls._parse_date(cls._tag(bloco, "DTPOSTED")),
                    valor=valor,
                    descricao=descricao.strip(),
                    tipo=cls._tag(bloco, "TRNTYPE"),
                    documento=cls._tag(bloco, "CHECKNUM") or cls._tag(bloco, "REFNUM"),
                    raw=raw,
                )
            )
        if not transacoes:
            raise OFXError("Nenhum lançamento foi encontrado no arquivo OFX.")
        return OFXDocument(
            origem=origem,
            instituicao=cls._tag(texto, "ORG") or cls._tag(texto, "FI"),
            banco=cls._tag(texto, "BANKID"),
            identificador_conta=cls._tag(texto, "ACCTID"),
            data_inicio=cls._parse_date(cls._tag(texto, "DTSTART")),
            data_fim=cls._parse_date(cls._tag(texto, "DTEND")),
            data_posicao=cls._parse_date(cls._tag(texto, "DTASOF")),
            saldo=cls._optional_decimal(cls._tag(texto, "BALAMT")),
            moeda=cls._tag(texto, "CURDEF"),
            transacoes=transacoes,
        )

    @staticmethod
    def _tag(bloco: str, nome: str) -> str:
        match = re.search(rf"<{nome}\b[^>]*>\s*([^\r\n<]+)", bloco, flags=re.I)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _parse_date(value: str) -> date | None:
        digits = re.sub(r"\D", "", value or "")
        if len(digits) < 8:
            return None
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _as_date(value) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        return value if isinstance(value, date) else None

    @staticmethod
    def _as_decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    @classmethod
    def _optional_decimal(cls, value: str) -> Decimal | None:
        return cls._as_decimal(value.replace(",", ".")) if value else None


class ContaOFXAdapter:
    origem = "CONTA"

    def normalize(self, documento: OFXDocument) -> OFXDocument:
        if documento.origem != self.origem:
            raise OFXError("O arquivo enviado não é um extrato de conta corrente.")
        return documento


class CartaoOFXAdapter:
    origem = "CARTAO"
    parcela_pattern = re.compile(r"(?<!\d)(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})(?!\d)", flags=re.I)

    def normalize(self, documento: OFXDocument) -> OFXDocument:
        if documento.origem != self.origem:
            raise OFXError("O arquivo enviado não é uma fatura de cartão.")
        return documento

    def installment(self, descricao: str) -> tuple[int | None, int | None]:
        match = self.parcela_pattern.search(descricao)
        if not match:
            return None, None
        numero, total = int(match.group(1)), int(match.group(2))
        if numero < 1 or total < numero or total > 99:
            return None, None
        return numero, total


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", ascii_value.upper())).strip()


def transaction_as_dict(transaction: OFXTransaction) -> dict:
    data = asdict(transaction)
    data["data"] = transaction.data.isoformat() if transaction.data else None
    data["valor"] = str(transaction.valor)
    return data


def preview_ofx(texto: str) -> list[OFXPreviewItem]:
    document = OFXParser.parse(texto)
    return [
        OFXPreviewItem(
            identificador=item.identificador,
            data=item.data.isoformat() if item.data else "",
            valor=item.valor,
            descricao=item.descricao,
        )
        for item in document.transacoes
    ]
