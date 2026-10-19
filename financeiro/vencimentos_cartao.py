from __future__ import annotations

from calendar import monthrange
from datetime import date
import re


CICLO_PATTERN = re.compile(r"^(?P<ano>\d{4})-(?P<mes>0[1-9]|1[0-2])$")


class VencimentoCartaoInvalido(ValueError):
    pass


def partes_ciclo(ciclo: str) -> tuple[int, int]:
    correspondencia = CICLO_PATTERN.fullmatch(str(ciclo or ""))
    if not correspondencia:
        raise VencimentoCartaoInvalido("O ciclo da fatura deve estar no formato AAAA-MM.")
    return int(correspondencia.group("ano")), int(correspondencia.group("mes"))


def calcular_vencimento_ciclo(ciclo: str, dia_vencimento: int) -> date:
    if not dia_vencimento or not 1 <= int(dia_vencimento) <= 31:
        raise VencimentoCartaoInvalido("O cartão deve possuir dia de vencimento entre 1 e 31.")
    ano, mes = partes_ciclo(ciclo)
    dia = min(int(dia_vencimento), monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def validar_vencimento_no_ciclo(ciclo: str, vencimento: date) -> None:
    ano, mes = partes_ciclo(ciclo)
    if not vencimento or (vencimento.year, vencimento.month) != (ano, mes):
        raise VencimentoCartaoInvalido("O vencimento deve pertencer ao mesmo mês e ano do ciclo da fatura.")


def resolver_vencimento_fatura(fatura) -> date:
    if fatura.vencimento:
        validar_vencimento_no_ciclo(fatura.ciclo, fatura.vencimento)
        return fatura.vencimento
    return calcular_vencimento_ciclo(fatura.ciclo, fatura.cartao.dia_vencimento)
