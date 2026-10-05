from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import CartaoForm, CategoriaForm, ContaForm, EventoFinanceiroForm, ImportacaoOFXForm, PessoaForm
from .models import Cartao, Categoria, Conta, EventoFinanceiro, Fatura, Importacao, ItemImportacao, MovimentoConta, Pessoa
from .ofx import preview_ofx


class UsuarioMixin:
    def get_queryset(self):
        return super().get_queryset().filter(usuario=self.request.user)

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        return super().form_valid(form)


@login_required
def dashboard(request):
    eventos = EventoFinanceiro.objects.filter(usuario=request.user)
    movimentos = MovimentoConta.objects.filter(conta__usuario=request.user)
    contexto = {
        "total_contas": Conta.objects.filter(usuario=request.user, ativa=True).count(),
        "total_cartoes": Cartao.objects.filter(usuario=request.user, ativo=True).count(),
        "total_pendentes": eventos.filter(situacao="PENDENTE").count(),
        "saldo_movimentos": movimentos.aggregate(total=Sum("valor"))["total"] or 0,
        "faturas": Fatura.objects.filter(usuario=request.user).select_related("cartao")[:6],
        "eventos": eventos.select_related("pessoa")[:12],
    }
    return render(request, "financeiro/dashboard.html", contexto)


class ContaListView(UsuarioMixin, ListView):
    model = Conta
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    extra_context = {"titulo": "Contas financeiras", "novo_url": "conta_nova"}


class ContaCreateView(UsuarioMixin, CreateView):
    model = Conta
    form_class = ContaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("contas")
    extra_context = {"titulo": "Nova conta financeira"}


class ContaUpdateView(UsuarioMixin, UpdateView):
    model = Conta
    form_class = ContaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("contas")
    extra_context = {"titulo": "Editar conta financeira"}


class CartaoListView(UsuarioMixin, ListView):
    model = Cartao
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    extra_context = {"titulo": "Cartoes", "novo_url": "cartao_novo"}


class CartaoCreateView(UsuarioMixin, CreateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("cartoes")
    extra_context = {"titulo": "Novo cartao"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class CartaoUpdateView(UsuarioMixin, UpdateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("cartoes")
    extra_context = {"titulo": "Editar cartao"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class CategoriaListView(UsuarioMixin, ListView):
    model = Categoria
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    extra_context = {"titulo": "Categorias", "novo_url": "categoria_nova"}


class CategoriaCreateView(UsuarioMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("categorias")
    extra_context = {"titulo": "Nova categoria"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class CategoriaUpdateView(UsuarioMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("categorias")
    extra_context = {"titulo": "Editar categoria"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class PessoaListView(UsuarioMixin, ListView):
    model = Pessoa
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    extra_context = {"titulo": "Pessoas", "novo_url": "pessoa_nova"}


class PessoaCreateView(UsuarioMixin, CreateView):
    model = Pessoa
    form_class = PessoaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("pessoas")
    extra_context = {"titulo": "Nova pessoa"}


class EventoListView(UsuarioMixin, ListView):
    model = EventoFinanceiro
    template_name = "financeiro/eventos.html"
    context_object_name = "eventos"


class EventoCreateView(UsuarioMixin, CreateView):
    model = EventoFinanceiro
    form_class = EventoFinanceiroForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("eventos")
    extra_context = {"titulo": "Novo lancamento"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


@login_required
def importar_ofx(request):
    previa = []
    importacao = None
    if request.method == "POST":
        form = ImportacaoOFXForm(request.POST, request.FILES, usuario=request.user)
        if form.is_valid():
            arquivo = form.cleaned_data["arquivo_ofx"]
            texto = arquivo.read().decode("latin-1", errors="ignore")
            arquivo.seek(0)
            previa = preview_ofx(texto)
            importacao = form.save()
            for indice, item in enumerate(previa, start=1):
                ItemImportacao.objects.create(
                    importacao=importacao,
                    identificador_externo=item.identificador,
                    ocorrencia=indice,
                    data=item.data or None,
                    valor=item.valor,
                    descricao_original=item.descricao,
                    registro_original={"origem": "preview_ofx"},
                    status=ItemImportacao.Status.PENDENTE,
                )
            return redirect("importacao_revisao", pk=importacao.pk)
    else:
        form = ImportacaoOFXForm(usuario=request.user)
    return render(request, "financeiro/importar.html", {"form": form, "previa": previa, "importacao": importacao})


@login_required
def importacao_revisao(request, pk):
    importacao = Importacao.objects.filter(usuario=request.user).get(pk=pk)
    itens = importacao.itens.all()
    return render(request, "financeiro/importacao_revisao.html", {"importacao": importacao, "itens": itens})
