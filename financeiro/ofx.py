from dataclasses import dataclass
from decimal import Decimal
import re


@dataclass(frozen=True)
class OFXPreviewItem:
    identificador: str
    data: str
    valor: Decimal
    descricao: str


def preview_ofx(texto: str) -> list[OFXPreviewItem]:
    """Extrai uma previa simples de STMTTRN/CCSTMTTRN sem confirmar importacao."""
    blocos = re.findall(r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)", texto, flags=re.I | re.S)
    if not blocos:
        blocos = re.findall(r"<CCSTMTTRN>(.*?)(?=<CCSTMTTRN>|</BANKTRANLIST>|$)", texto, flags=re.I | re.S)
    return [item for bloco in blocos if (item := _parse_bloco(bloco))]


def _tag(bloco: str, nome: str) -> str:
    match = re.search(rf"<{nome}>([^\r\n<]+)", bloco, flags=re.I)
    return match.group(1).strip() if match else ""


def _parse_bloco(bloco: str) -> OFXPreviewItem | None:
    valor_raw = _tag(bloco, "TRNAMT")
    if not valor_raw:
        return None
    data = _tag(bloco, "DTPOSTED")[:8]
    descricao = _tag(bloco, "MEMO") or _tag(bloco, "NAME") or "Sem descricao"
    identificador = _tag(bloco, "FITID")
    return OFXPreviewItem(
        identificador=identificador,
        data=f"{data[:4]}-{data[4:6]}-{data[6:8]}" if len(data) == 8 else "",
        valor=Decimal(valor_raw.replace(",", ".")),
        descricao=descricao,
    )
