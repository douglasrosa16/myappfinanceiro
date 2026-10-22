from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrar_regras_categoria(apps, schema_editor):
    RegraCategoria = apps.get_model("financeiro", "RegraCategoria")
    RegraCategoriaCondicao = apps.get_model("financeiro", "RegraCategoriaCondicao")

    for regra in RegraCategoria.objects.all().iterator():
        texto = (regra.texto or "").strip()
        regra.nome = texto or f"Regra {regra.pk}"
        regra.prioridade = 100
        regra.combinador = "TODAS"
        regra.versao_motor = "LEGADO"
        regra.save(update_fields=["nome", "prioridade", "combinador", "versao_motor"])
        RegraCategoriaCondicao.objects.get_or_create(
            regra_id=regra.pk,
            ordem=1,
            defaults={
                "campo": "DESCRICAO",
                "operador": "CONTEM",
                "valor": texto or regra.nome,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0016_vinculo_titulo_importacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="regracategoria",
            name="texto",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="regracategoria",
            name="nome",
            field=models.CharField(default="", max_length=160),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="regracategoria",
            name="prioridade",
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="regracategoria",
            name="combinador",
            field=models.CharField(
                choices=[("TODAS", "Todas as condições (E)"), ("QUALQUER", "Qualquer condição (OU)")],
                default="TODAS",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="regracategoria",
            name="versao_motor",
            field=models.CharField(
                choices=[("LEGADO", "Legada — em uso"), ("NOVO", "Nova — aguardando integração")],
                default="LEGADO",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="regracategoria",
            name="natureza_sugerida",
            field=models.CharField(
                blank=True,
                choices=[("DESPESA", "Despesa"), ("RECEITA", "Receita"), ("ESTORNO", "Estorno")],
                default="",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="regracategoria",
            name="ambito",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PESSOAL", "Pessoal"),
                    ("PROFISSIONAL", "Profissional"),
                    ("NAO_DEFINIDO", "Nao definido"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="regracategoria",
            name="categoria",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="financeiro.categoria",
            ),
        ),
        migrations.AlterModelOptions(
            name="regracategoria",
            options={"ordering": ["prioridade", "id"]},
        ),
        migrations.AddIndex(
            model_name="regracategoria",
            index=models.Index(
                fields=["usuario", "versao_motor", "ativa", "prioridade"],
                name="fin_regra_usr_ver_at_pr_idx",
            ),
        ),
        migrations.CreateModel(
            name="RegraCategoriaCondicao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("ordem", models.PositiveSmallIntegerField(default=1)),
                (
                    "campo",
                    models.CharField(
                        choices=[
                            ("DESCRICAO", "Descrição"),
                            ("OBSERVACAO", "Observação"),
                            ("VALOR", "Valor absoluto"),
                            ("NATUREZA", "Tipo atual"),
                            ("ORIGEM", "Origem"),
                            ("CONTA", "Conta específica"),
                            ("CARTAO", "Cartão específico"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "operador",
                    models.CharField(
                        choices=[
                            ("CONTEM", "contém"),
                            ("NAO_CONTEM", "não contém"),
                            ("IGUAL", "é igual a"),
                            ("DIFERENTE", "é diferente de"),
                            ("COMECA_COM", "começa com"),
                            ("TERMINA_COM", "termina com"),
                            ("MAIOR", "é maior que"),
                            ("MAIOR_IGUAL", "é maior ou igual a"),
                            ("MENOR", "é menor que"),
                            ("MENOR_IGUAL", "é menor ou igual a"),
                        ],
                        max_length=20,
                    ),
                ),
                ("valor", models.CharField(max_length=255)),
                (
                    "regra",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="condicoes",
                        to="financeiro.regracategoria",
                    ),
                ),
            ],
            options={"ordering": ["ordem", "id"]},
        ),
        migrations.AddConstraint(
            model_name="regracategoriacondicao",
            constraint=models.UniqueConstraint(
                fields=("regra", "ordem"),
                name="uniq_regra_categoria_condicao_ordem",
            ),
        ),
        migrations.AddIndex(
            model_name="regracategoriacondicao",
            index=models.Index(fields=["regra", "campo"], name="fin_regra_cond_reg_campo_idx"),
        ),
        migrations.RunPython(migrar_regras_categoria, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="regracategoria",
            name="versao_motor",
            field=models.CharField(
                choices=[("LEGADO", "Legada — em uso"), ("NOVO", "Nova — aguardando integração")],
                default="NOVO",
                max_length=20,
            ),
        ),
    ]
