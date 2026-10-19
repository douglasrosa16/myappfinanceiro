import unicodedata

from django.db import migrations, models


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(caractere for caractere in texto if not unicodedata.combining(caractere)).casefold().strip()


def migrar_categorias(apps, schema_editor):
    Categoria = apps.get_model("financeiro", "Categoria")
    Categoria.objects.filter(tipo="AMBOS").update(tipo="DESPESA")

    nomes_neutros = {"pagamento de fatura", "dinheiro em especie", "saque em dinheiro"}
    for categoria in Categoria.objects.all().only("pk", "nome"):
        nome = _normalizar(categoria.nome)
        if nome in nomes_neutros or "transferencia" in nome:
            Categoria.objects.filter(pk=categoria.pk).update(
                tipo="TRANSFERENCIA",
                essencialidade="NEUTRO",
                computa_resultado=False,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0009_normalizar_status_faturas_abertas"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="natureza",
            field=models.CharField(
                choices=[
                    ("PESSOAL", "Pessoal"),
                    ("EMPRESARIAL", "Empresarial"),
                    ("AMBOS", "Pessoal / Empresarial"),
                ],
                default="PESSOAL",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="categoria",
            name="essencialidade",
            field=models.CharField(
                choices=[
                    ("ESSENCIAL", "Essencial"),
                    ("NECESSARIO_VARIAVEL", "Necessário variável"),
                    ("PROFISSIONAL", "Profissional"),
                    ("ESTILO_VIDA", "Estilo de vida"),
                    ("SUPERFLUO", "Supérfluo"),
                    ("FINANCEIRO", "Financeiro"),
                    ("NEUTRO", "Neutro"),
                ],
                default="NECESSARIO_VARIAVEL",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="categoria",
            name="computa_resultado",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(migrar_categorias, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="categoria",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("DESPESA", "Despesa"),
                    ("RECEITA", "Receita"),
                    ("TRANSFERENCIA", "Transferência"),
                ],
                default="DESPESA",
                max_length=20,
            ),
        ),
    ]
