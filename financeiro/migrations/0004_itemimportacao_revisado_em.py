from django.db import migrations, models
from django.db.models import F


MOTIVOS_REVISAO_MANUAL = (
    "Revisado pelo usuário.",
    "Divergência aceita e vinculada pelo usuário.",
)


def marcar_revisoes_existentes(apps, schema_editor):
    item_importacao = apps.get_model("financeiro", "ItemImportacao")
    item_importacao.objects.filter(motivo_status__in=MOTIVOS_REVISAO_MANUAL).update(
        revisado_em=F("atualizado_em")
    )


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0003_itemimportacao_observacao")]

    operations = [
        migrations.AddField(
            model_name="itemimportacao",
            name="revisado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(marcar_revisoes_existentes, migrations.RunPython.noop),
    ]
