from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def brl(value):
    if value in (None, ""):
        return "R$ 0,00"
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


@register.filter
def brl_sinal(value):
    if value in (None, ""):
        return "R$ 0,00"
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    prefixo = "-" if number < 0 else ""
    formatted = f"{abs(number):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefixo}R$ {formatted}"


@register.filter
def classe_valor(value, semantica="saldo"):
    """Retorna a classe visual de um valor monetário sem colorir valores neutros."""
    if value in (None, ""):
        return ""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if number == 0:
        return ""
    if semantica in {"saida", "PAGAR"}:
        return "amount-negative" if number > 0 else "amount-positive"
    return "amount-positive" if number > 0 else "amount-negative"
