import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0001_initial")]

    operations = [
        migrations.AlterModelOptions(name="itemimportacao", options={"ordering": ["posicao", "id"]}),
        migrations.RemoveConstraint(model_name="importacao", name="uniq_importacao_usuario_hash"),
        migrations.RemoveConstraint(model_name="itemimportacao", name="uniq_item_importacao_ocorrencia"),
        migrations.AddField(
            model_name="compracartao",
            name="valor_total_estimado",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(model_name="importacao", name="data_fim", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="importacao", name="data_inicio", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="importacao", name="data_posicao", field=models.DateField(blank=True, null=True)),
        migrations.AddField(
            model_name="importacao",
            name="identificador_conta",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="importacao",
            name="saldo_informado",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="importacao",
            name="total_creditos",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="importacao",
            name="total_debitos",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="importacao",
            name="total_liquido",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="itemimportacao",
            name="acao",
            field=models.CharField(
                choices=[("CRIAR", "Criar lançamento"), ("VINCULAR", "Vincular existente"), ("IGNORAR", "Ignorar")],
                default="CRIAR",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="itemimportacao",
            name="ambito",
            field=models.CharField(
                choices=[("PESSOAL", "Pessoal"), ("PROFISSIONAL", "Profissional"), ("NAO_DEFINIDO", "Nao definido")],
                default="NAO_DEFINIDO",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="itemimportacao",
            name="categoria",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.categoria"),
        ),
        migrations.AddField(model_name="itemimportacao", name="chave_conciliacao", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="itemimportacao", name="data_revisada", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="itemimportacao", name="descricao_revisada", field=models.CharField(blank=True, max_length=220)),
        migrations.AddField(model_name="itemimportacao", name="documento", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="itemimportacao", name="motivo_status", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="itemimportacao",
            name="natureza",
            field=models.CharField(
                blank=True,
                choices=[
                    ("DESPESA", "Despesa"),
                    ("RECEITA", "Receita"),
                    ("ESTORNO", "Estorno"),
                    ("PAGAMENTO_FATURA", "Pagamento de fatura"),
                    ("TRANSFERENCIA", "Transferencia"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(model_name="itemimportacao", name="numero_parcela", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(
            model_name="itemimportacao",
            name="pessoa",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="financeiro.pessoa"),
        ),
        migrations.AddField(model_name="itemimportacao", name="posicao", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="itemimportacao", name="tipo_normalizado", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="itemimportacao", name="total_parcelas", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(
            model_name="itemimportacao",
            name="valor_revisado",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddIndex(
            model_name="importacao",
            index=models.Index(fields=["usuario", "hash_arquivo"], name="financeiro__usuario_b2e3f4_idx"),
        ),
        migrations.AddIndex(
            model_name="importacao",
            index=models.Index(fields=["usuario", "origem", "status"], name="financeiro__usuario_f52f47_idx"),
        ),
        migrations.AddIndex(
            model_name="itemimportacao",
            index=models.Index(fields=["importacao", "status"], name="financeiro__importa_415e52_idx"),
        ),
        migrations.AddIndex(
            model_name="itemimportacao",
            index=models.Index(fields=["chave_conciliacao"], name="financeiro__chave_c_1a7a70_idx"),
        ),
        migrations.AddIndex(
            model_name="itemimportacao",
            index=models.Index(fields=["identificador_externo"], name="financeiro__identif_8f6155_idx"),
        ),
        migrations.AddConstraint(
            model_name="importacao",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("cartao__isnull", True), ("ciclo", ""), ("conta__isnull", False), ("origem", "CONTA")),
                    models.Q(
                        ("cartao__isnull", False),
                        ("conta__isnull", True),
                        ("origem", "CARTAO"),
                        models.Q(("ciclo", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="check_importacao_origem_destino",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemimportacao",
            constraint=models.UniqueConstraint(fields=("importacao", "posicao"), name="uniq_item_importacao_posicao"),
        ),
        migrations.AddConstraint(
            model_name="liquidacao",
            constraint=models.UniqueConstraint(
                condition=models.Q(("movimento_conta__isnull", False)),
                fields=("movimento_conta",),
                name="uniq_liquidacao_movimento_conta",
            ),
        ),
    ]
