import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q
from django.utils.text import slugify


def preencher_codigos_categorias(apps, schema_editor):
    categoria_model = apps.get_model("financeiro", "Categoria")
    usados_por_usuario = {}
    for categoria in categoria_model.objects.order_by("usuario_id", "id").iterator():
        usados = usados_por_usuario.setdefault(categoria.usuario_id, set())
        base = slugify(categoria.nome)[:120] or "categoria"
        codigo = base
        sufixo = 2
        while codigo in usados:
            codigo = f"{base[:130 - len(str(sufixo))]}-{sufixo}"
            sufixo += 1
        categoria_model.objects.filter(pk=categoria.pk).update(codigo=codigo)
        usados.add(codigo)


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0005_parcela_dados_editaveis")]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="codigo",
            field=models.SlugField(blank=True, max_length=140),
        ),
        migrations.RunPython(preencher_codigos_categorias, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="categoria",
            constraint=models.UniqueConstraint(
                fields=("usuario", "codigo"),
                condition=~Q(codigo=""),
                name="uniq_categoria_usuario_codigo",
            ),
        ),
        migrations.AddField(
            model_name="titulo",
            name="evento",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="titulo_previsto",
                to="financeiro.eventofinanceiro",
            ),
        ),
        migrations.AddIndex(
            model_name="titulo",
            index=models.Index(
                fields=["usuario", "tipo", "vencimento"],
                condition=Q(ativo=True),
                name="idx_titulo_pendente",
            ),
        ),
    ]
