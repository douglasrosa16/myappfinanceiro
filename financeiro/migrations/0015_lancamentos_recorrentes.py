from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0014_remover_observacoes_automaticas_importacao"),
    ]

    operations = [
        migrations.CreateModel(
            name="SerieLancamentoRecorrente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("quantidade_ocorrencias", models.PositiveSmallIntegerField()),
                ("intervalo_meses", models.PositiveSmallIntegerField()),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="serielancamentorecorrente",
            index=models.Index(fields=["usuario", "criado_em"], name="financeiro__usuario_34a003_idx"),
        ),
        migrations.AddField(
            model_name="eventofinanceiro",
            name="numero_recorrencia",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventofinanceiro",
            name="serie_recorrente",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="eventos", to="financeiro.serielancamentorecorrente"),
        ),
        migrations.AddConstraint(
            model_name="eventofinanceiro",
            constraint=models.UniqueConstraint(fields=("serie_recorrente", "numero_recorrencia"), name="uniq_evento_serie_recorrencia_numero"),
        ),
    ]
