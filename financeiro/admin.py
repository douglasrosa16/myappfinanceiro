from django.contrib import admin

from . import models


@admin.register(models.Conta)
class ContaAdmin(admin.ModelAdmin):
    list_display = ("nome", "banco", "tipo", "ambito", "ativa")
    list_filter = ("tipo", "ambito", "ativa")
    search_fields = ("nome", "banco", "numero", "titular")


@admin.register(models.Cartao)
class CartaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "emissor", "final", "dia_fechamento", "dia_vencimento", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "emissor", "identificador_externo", "final")


@admin.register(models.Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "categoria_pai", "ativa")
    list_filter = ("tipo", "ativa")
    search_fields = ("nome",)


@admin.register(models.Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome", "documento", "ativa")
    search_fields = ("nome", "documento")


class RegraCategoriaCondicaoInline(admin.TabularInline):
    model = models.RegraCategoriaCondicao
    extra = 0


@admin.register(models.RegraCategoria)
class RegraCategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "usuario", "prioridade", "versao_motor", "ativa")
    list_filter = ("versao_motor", "ativa", "combinador")
    search_fields = ("nome", "texto", "usuario__username")
    inlines = (RegraCategoriaCondicaoInline,)


admin.site.register(models.Fatura)
admin.site.register(models.EventoFinanceiro)
admin.site.register(models.RateioCategoria)
admin.site.register(models.MovimentoConta)
admin.site.register(models.CompraCartao)
admin.site.register(models.ParcelaCartao)
admin.site.register(models.Titulo)
admin.site.register(models.Liquidacao)
admin.site.register(models.Importacao)
admin.site.register(models.ItemImportacao)
admin.site.register(models.Orcamento)
