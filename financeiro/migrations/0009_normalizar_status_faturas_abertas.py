from django.db import migrations


def normalizar_faturas_parciais_sem_titulo(apps, schema_editor):
    Fatura = apps.get_model("financeiro", "Fatura")
    Titulo = apps.get_model("financeiro", "Titulo")
    faturas_com_titulo = Titulo.objects.exclude(fatura_id=None).values("fatura_id")
    Fatura.objects.filter(status="PARCIAL").exclude(id__in=faturas_com_titulo).update(status="ABERTA")


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0008_pessoa_nome_livre_lancamentos"),
    ]

    operations = [
        migrations.RunPython(normalizar_faturas_parciais_sem_titulo, migrations.RunPython.noop),
    ]
