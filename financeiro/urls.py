from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("contas/", views.ContaListView.as_view(), name="contas"),
    path("contas/nova/", views.ContaCreateView.as_view(), name="conta_nova"),
    path("contas/<int:pk>/editar/", views.ContaUpdateView.as_view(), name="conta_editar"),
    path("cartoes/", views.CartaoListView.as_view(), name="cartoes"),
    path("cartoes/novo/", views.CartaoCreateView.as_view(), name="cartao_novo"),
    path("cartoes/<int:pk>/editar/", views.CartaoUpdateView.as_view(), name="cartao_editar"),
    path("categorias/", views.CategoriaListView.as_view(), name="categorias"),
    path("categorias/nova/", views.CategoriaCreateView.as_view(), name="categoria_nova"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_editar"),
    path("pessoas/", views.PessoaListView.as_view(), name="pessoas"),
    path("pessoas/nova/", views.PessoaCreateView.as_view(), name="pessoa_nova"),
    path("lancamentos/", views.EventoListView.as_view(), name="eventos"),
    path("lancamentos/novo/", views.EventoCreateView.as_view(), name="evento_novo"),
    path("importar/ofx/", views.importar_ofx, name="importar_ofx"),
    path("importar/<int:pk>/revisao/", views.importacao_revisao, name="importacao_revisao"),
]
