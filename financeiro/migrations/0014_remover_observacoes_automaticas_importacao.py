from django.db import migrations


MARCADOR_IMPORTACAO = "importado do lote #"


def remover_observacoes_automaticas(apps, schema_editor):
    EventoFinanceiro = apps.get_model("financeiro", "EventoFinanceiro")
    alias = schema_editor.connection.alias
    atualizacoes = []

    eventos = (
        EventoFinanceiro.objects.using(alias)
        .filter(observacao__icontains="Importado do lote #")
        .order_by("pk")
    )
    for evento in eventos.iterator():
        observacao = evento.observacao or ""
        posicao = observacao.casefold().find(MARCADOR_IMPORTACAO)
        if posicao < 0:
            continue
        evento.observacao = observacao[:posicao].rstrip()
        atualizacoes.append(evento)

    if atualizacoes:
        EventoFinanceiro.objects.using(alias).bulk_update(
            atualizacoes,
            ["observacao"],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0013_vencimento_obrigatorio_parcelas"),
    ]

    operations = [
        migrations.RunPython(remover_observacoes_automaticas, migrations.RunPython.noop),
    ]
