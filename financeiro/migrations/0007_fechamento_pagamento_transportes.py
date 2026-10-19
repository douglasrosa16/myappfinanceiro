import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count, Q


def preparar_dados_existentes(apps, schema_editor):
    Fatura = apps.get_model("financeiro", "Fatura")
    Titulo = apps.get_model("financeiro", "Titulo")
    duplicados = (
        Titulo.objects.filter(fatura__isnull=False)
        .values("fatura_id")
        .annotate(quantidade=Count("id"))
        .filter(quantidade__gt=1)
    )
    if duplicados.exists():
        raise RuntimeError("Existem títulos históricos duplicados por fatura; resolva-os antes desta migration.")
    Fatura.objects.all().update(total_exigido=models.F("total"))
    Titulo.objects.filter(ativo=True).update(status="ABERTO")
    Titulo.objects.filter(ativo=False).update(status="LIQUIDADO")


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0006_dashboard_visao_geral"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.AddField(
            model_name="fatura",
            name="total_exigido",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="fatura",
            name="total_transportado",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name="fatura",
            name="status",
            field=models.CharField(choices=[("ABERTA", "Aberta"), ("FECHADA", "Fechada"), ("PAGA", "Paga"), ("PARCIAL", "Parcial"), ("EM_CORRECAO", "Em correção")], default="ABERTA", max_length=20),
        ),
        migrations.AlterField(
            model_name="parcelacartao",
            name="situacao",
            field=models.CharField(choices=[("REALIZADO", "Realizado"), ("PREVISTO", "Previsto"), ("PENDENTE", "Pendente"), ("CANCELADO", "Cancelado")], default="REALIZADO", max_length=20),
        ),
        migrations.AlterField(
            model_name="eventofinanceiro",
            name="situacao",
            field=models.CharField(choices=[("REALIZADO", "Realizado"), ("PREVISTO", "Previsto"), ("PENDENTE", "Pendente"), ("CANCELADO", "Cancelado")], default="REALIZADO", max_length=20),
        ),
        migrations.AddField(
            model_name="movimentoconta",
            name="chave_idempotencia",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="titulo",
            name="status",
            field=models.CharField(choices=[("ABERTO", "Aberto"), ("SUSPENSO", "Suspenso"), ("LIQUIDADO", "Liquidado")], default="ABERTO", max_length=20),
        ),
        migrations.AddField(
            model_name="titulo",
            name="valor_transportado",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="liquidacao",
            name="chave_idempotencia",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="liquidacao",
            name="origem",
            field=models.CharField(choices=[("CONCILIACAO", "Conciliação"), ("MANUAL", "Manual"), ("IMPORTACAO", "Importação")], default="CONCILIACAO", max_length=20),
        ),
        migrations.AddField(
            model_name="liquidacao",
            name="status",
            field=models.CharField(choices=[("ATIVA", "Ativa"), ("ESTORNADA", "Estornada")], default="ATIVA", max_length=20),
        ),
        migrations.RunPython(preparar_dados_existentes, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="titulo", name="uniq_titulo_ativo_por_fatura"),
        migrations.AddConstraint(
            model_name="titulo",
            constraint=models.UniqueConstraint(condition=Q(("fatura__isnull", False)), fields=("fatura",), name="uniq_titulo_por_fatura"),
        ),
        migrations.AddConstraint(
            model_name="movimentoconta",
            constraint=models.UniqueConstraint(condition=~Q(("chave_idempotencia", "")), fields=("conta", "chave_idempotencia"), name="uniq_movimento_conta_idempotencia"),
        ),
        migrations.RemoveConstraint(model_name="liquidacao", name="uniq_liquidacao_movimento_conta"),
        migrations.AddConstraint(
            model_name="liquidacao",
            constraint=models.UniqueConstraint(condition=Q(("movimento_conta__isnull", False), ("status", "ATIVA")), fields=("titulo", "movimento_conta"), name="uniq_liquidacao_ativa_titulo_movimento"),
        ),
        migrations.AddConstraint(
            model_name="liquidacao",
            constraint=models.UniqueConstraint(condition=~Q(("chave_idempotencia", "")), fields=("titulo", "chave_idempotencia"), name="uniq_liquidacao_titulo_idempotencia"),
        ),
        migrations.CreateModel(
            name="FechamentoFatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("versao", models.PositiveIntegerField()),
                ("total_bruto", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_creditos", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_proprio", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_transportado", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_exigido", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("vencimento", models.DateField()),
                ("status", models.CharField(choices=[("ATIVO", "Ativo"), ("REABERTO", "Reaberto"), ("SUBSTITUIDO", "Substituído")], default="ATIVO", max_length=20)),
                ("observacao", models.TextField(blank=True)),
                ("conta_pagamento", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.conta")),
                ("fatura", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fechamentos", to="financeiro.fatura")),
            ],
            options={"ordering": ["fatura_id", "-versao"]},
        ),
        migrations.AddConstraint(model_name="fechamentofatura", constraint=models.UniqueConstraint(fields=("fatura", "versao"), name="uniq_fechamento_fatura_versao")),
        migrations.CreateModel(
            name="HistoricoFatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("evento", models.CharField(choices=[("FECHAMENTO", "Fechamento"), ("REABERTURA", "Reabertura"), ("CORRECAO", "Correção"), ("PROGRAMACAO", "Programação"), ("LIQUIDACAO", "Liquidação"), ("TRANSPORTE_SAIDA", "Saldo transportado"), ("TRANSPORTE_ENTRADA", "Saldo recebido")], max_length=30)),
                ("valor", models.DecimalField(decimal_places=2, default=0, max_digits=14)), ("descricao", models.CharField(max_length=255)), ("dados", models.JSONField(blank=True, default=dict)),
                ("fatura", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="historico", to="financeiro.fatura")),
            ], options={"ordering": ["-criado_em", "-id"]},
        ),
        migrations.CreateModel(
            name="ItemFechamentoFatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("descricao", models.CharField(max_length=220)), ("natureza", models.CharField(choices=[("DESPESA", "Despesa"), ("RECEITA", "Receita"), ("ESTORNO", "Estorno"), ("PAGAMENTO_FATURA", "Pagamento de fatura"), ("TRANSFERENCIA", "Transferencia")], max_length=30)), ("valor", models.DecimalField(decimal_places=2, max_digits=14)),
                ("fechamento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="financeiro.fechamentofatura")),
                ("parcela", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.parcelacartao")),
            ],
        ),
        migrations.CreateModel(
            name="ProgramacaoPagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("data_programada", models.DateField()), ("valor_programado", models.DecimalField(decimal_places=2, max_digits=14)), ("valor_realizado", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("ATIVA", "Ativa"), ("PARCIAL", "Parcial"), ("CONCLUIDA", "Concluída"), ("CANCELADA", "Cancelada"), ("SUBSTITUIDA", "Substituída")], default="ATIVA", max_length=20)),
                ("chave_idempotencia", models.CharField(blank=True, max_length=80)), ("observacao", models.TextField(blank=True)),
                ("conta", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="financeiro.conta")),
                ("titulo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="programacoes", to="financeiro.titulo")),
            ], options={"ordering": ["data_programada", "id"]},
        ),
        migrations.AddConstraint(model_name="programacaopagamento", constraint=models.UniqueConstraint(condition=~Q(("chave_idempotencia", "")), fields=("titulo", "chave_idempotencia"), name="uniq_programacao_titulo_idempotencia")),
        migrations.CreateModel(
            name="AplicacaoLiquidacaoProgramacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)), ("valor", models.DecimalField(decimal_places=2, max_digits=14)),
                ("liquidacao", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicacoes_programacao", to="financeiro.liquidacao")),
                ("programacao", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicacoes", to="financeiro.programacaopagamento")),
            ],
        ),
        migrations.AddConstraint(model_name="aplicacaoliquidacaoprogramacao", constraint=models.UniqueConstraint(fields=("liquidacao", "programacao"), name="uniq_aplicacao_liquidacao_programacao")),
        migrations.CreateModel(
            name="EvidenciaLiquidacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("tipo", models.CharField(choices=[("OFX_CONTA", "OFX conta"), ("OFX_CARTAO", "OFX cartão"), ("MANUAL", "Manual")], max_length=20)), ("chave", models.CharField(max_length=100)), ("dados", models.JSONField(blank=True, default=dict)),
                ("liquidacao", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evidencias", to="financeiro.liquidacao")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="evidencialiquidacao", constraint=models.UniqueConstraint(fields=("usuario", "tipo", "chave"), name="uniq_evidencia_liquidacao")),
        migrations.CreateModel(
            name="SaldoTransportadoFatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("criado_em", models.DateTimeField(auto_now_add=True)), ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=14)), ("data_identificacao", models.DateField()),
                ("status", models.CharField(choices=[("IDENTIFICADO", "Identificado"), ("CONFIRMADO", "Confirmado"), ("INCORPORADO", "Incorporado"), ("CANCELADO", "Cancelado")], default="IDENTIFICADO", max_length=20)),
                ("chave_idempotencia", models.CharField(blank=True, max_length=100)), ("observacao", models.TextField(blank=True)),
                ("evidencia", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.evidencialiquidacao")),
                ("fatura_destino", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transportes_entrada", to="financeiro.fatura")),
                ("fatura_origem", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transportes_saida", to="financeiro.fatura")),
                ("titulo_destino", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="transportes_entrada", to="financeiro.titulo")),
                ("titulo_origem", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transportes_saida", to="financeiro.titulo")),
            ],
        ),
        migrations.AddIndex(model_name="saldotransportadofatura", index=models.Index(fields=["fatura_origem", "status"], name="financeiro__fatura__dca5c3_idx")),
        migrations.AddIndex(model_name="saldotransportadofatura", index=models.Index(fields=["fatura_destino", "status"], name="financeiro__fatura__0d46db_idx")),
        migrations.AddConstraint(model_name="saldotransportadofatura", constraint=models.UniqueConstraint(condition=~Q(("chave_idempotencia", "")), fields=("titulo_origem", "chave_idempotencia"), name="uniq_transporte_origem_idempotencia")),
        migrations.AddField(
            model_name="itemimportacao",
            name="evidencia_liquidacao",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.evidencialiquidacao"),
        ),
    ]
