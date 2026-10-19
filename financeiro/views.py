from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, ProtectedError, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, ListView, UpdateView
from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

from .forms import (
    AplicacaoLoteForm,
    CartaoForm,
    CategoriaForm,
    CompraCartaoForm,
    ContaForm,
    ImportacaoOFXForm,
    ImportacaoPlanilhaForm,
    ItemImportacaoForm,
    LancamentoForm,
    FechamentoFaturaForm,
    ProgramacaoPagamentoForm,
    ConciliacaoPagamentoForm,
    PagamentoManualFaturaForm,
    TransporteSaldoFaturaForm,
    ReaberturaFaturaForm,
    PessoaForm,
)
from .models import Cartao, Categoria, Conta, EventoFinanceiro, Fatura, Importacao, ItemImportacao, Liquidacao, ParcelaCartao, Pessoa, Situacao, Titulo, VinculoTituloImportacao
from .ofx import OFXError, OFXParser
from .services.cartoes_faturas import (
    aviso_ciclo_cartao,
    consultar_cartoes_faturas,
    criar_compra_cartao,
    editar_parcela_cartao,
    sincronizar_vencimentos_faturas_abertas_cartao,
)
from .services.dashboard import consultar_dashboard
from .services.importacao_ofx import (
    aplicar_alteracoes_lote,
    atualizar_status_revisao,
    buscar_candidatos_vinculo,
    confirmar_importacao,
    criar_itens,
    desfazer_importacao,
    resumo_importacao,
    selecionar_vinculo_item,
    sincronizar_titulos_multiplos,
)
from .services.importacao_planilha import criar_itens_planilha, ler_compras_planilha
from .services.parcelas_futuras import consultar_parcelas_futuras
from .services.saldo_contas import reprocessar_saldo_conta
from .services.lancamentos import (
    consultar_lancamentos,
    criar_lancamento,
    dados_edicao_lancamento,
    editar_lancamento_conta,
    excluir_lancamento_conta,
    excluir_parcela_lancamento,
    lancamento_possui_dados_protegidos,
    replicar_edicao_recorrencia,
)
from .services.detalhamento_dashboard import (
    DetalhamentoDashboardInvalido,
    consultar_detalhamento_dashboard,
)
from .services.fechamento_faturas import (
    fechar_fatura,
    programar_pagamento,
    conciliar_pagamento,
    registrar_pagamento_manual,
    criar_transporte,
    reabrir_fatura,
)


class UsuarioMixin(LoginRequiredMixin):
    def get_queryset(self):
        return super().get_queryset().filter(usuario=self.request.user)

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        return super().form_valid(form)


@login_required
def dashboard(request):
    contexto = consultar_dashboard(
        request.user,
        periodo=request.GET.get("period"),
        date_from=request.GET.get("date_from"),
        date_to=request.GET.get("date_to"),
        conta_id=request.GET.get("account"),
        cartao_id=request.GET.get("card"),
        origem=request.GET.get("origin", "all"),
        natureza=request.GET.get("nature", "all"),
    )
    return render(request, "financeiro/dashboard.html", contexto)


@login_required
@require_GET
def dashboard_detalhamento(request):
    try:
        contexto = consultar_detalhamento_dashboard(
            request.user,
            tipo=request.GET.get("type"),
            valor=request.GET.get("value", ""),
            periodo=request.GET.get("period"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
            conta_id=request.GET.get("account"),
            cartao_id=request.GET.get("card"),
            origem=request.GET.get("origin", "all"),
            natureza=request.GET.get("nature", "all"),
        )
    except DetalhamentoDashboardInvalido as exc:
        raise Http404("Detalhamento não encontrado.") from exc
    return render(request, "financeiro/_dashboard_detalhamento.html", contexto)


def _url_retorno_lancamento(request, periodo: str, destino_padrao="eventos"):
    destino = request.GET.get("return_to", destino_padrao)
    if destino not in {"dashboard", "eventos"}:
        destino = destino_padrao
    parametros = {"period": periodo}
    for origem, nome in (("account", "account"), ("card", "card")):
        valor = request.GET.get(origem)
        if valor and valor.isdigit():
            parametros[nome] = valor
    if destino == "dashboard":
        for nome in ("date_from", "date_to", "origin", "nature"):
            valor = request.GET.get(nome)
            if valor not in (None, ""):
                parametros[nome] = valor
    else:
        for nome in (
            "date_from",
            "date_to",
            "q",
            "origin",
            "category",
            "parent_category",
            "nature",
            "category_nature",
            "essentiality",
            "computes",
            "person",
            "status",
            "analysis_type",
            "analysis_value",
            "analysis_nature",
            "group_card_invoices",
        ):
            valor = request.GET.get(nome)
            if valor not in (None, ""):
                parametros[nome] = valor
    return f"{reverse(destino)}?{urlencode(parametros)}"


@login_required
def lancamentos(request):
    try:
        contexto = consultar_lancamentos(
            request.user,
            periodo=request.GET.get("period"),
            conta_id=request.GET.get("account"),
            cartao_id=request.GET.get("card"),
            busca=request.GET.get("q", ""),
            origem=request.GET.get("origin", "all"),
            categoria=request.GET.get("category", "all"),
            situacao=request.GET.get("status", "all"),
            data_inicial=request.GET.get("date_from"),
            data_final=request.GET.get("date_to"),
            categoria_superior=request.GET.get("parent_category", "all"),
            natureza=request.GET.get("nature", "all"),
            natureza_categoria=request.GET.get("category_nature", "all"),
            essencialidade=request.GET.get("essentiality", "all"),
            computa_resultado=request.GET.get("computes", "all"),
            pessoa=request.GET.get("person", "all"),
            analysis_type=request.GET.get("analysis_type", ""),
            analysis_value=request.GET.get("analysis_value", ""),
            analysis_nature=request.GET.get("analysis_nature", "all"),
            group_card_invoices=request.GET.get("group_card_invoices"),
        )
    except DetalhamentoDashboardInvalido as exc:
        raise Http404("Detalhamento não encontrado.") from exc
    return render(request, "financeiro/eventos.html", contexto)


@login_required
def lancamento_novo(request):
    periodo = request.GET.get("period")
    conta_id = request.GET.get("account")
    cartao_id = request.GET.get("card")
    clone_evento = None
    clone_initial = {}
    clone_id = request.GET.get("clone_evento")
    if clone_id and clone_id.isdigit():
        clone_evento = get_object_or_404(
            EventoFinanceiro.objects.prefetch_related("compras_cartao__parcelas", "rateios"),
            pk=int(clone_id),
            usuario=request.user,
        )
        clone_initial = dados_clonagem_lancamento(clone_evento)
        # A clonagem exige que a nova data seja informada manualmente.
        periodo = None
        if clone_initial.get("conta"):
            conta_id = str(clone_initial["conta"].pk)
        if clone_initial.get("cartao"):
            cartao_id = str(clone_initial["cartao"].pk)
    conta_preferida = Conta.objects.filter(
        usuario=request.user,
        ativa=True,
        pk=int(conta_id),
    ).first() if conta_id and conta_id.isdigit() else None
    cartao_preferido = Cartao.objects.filter(
        usuario=request.user,
        ativo=True,
        pk=int(cartao_id),
    ).first() if cartao_id and cartao_id.isdigit() else None
    kwargs = {
        "usuario": request.user,
        "periodo": periodo,
        "conta_preferida": conta_preferida,
        "cartao_preferido": cartao_preferido,
    }
    if request.method == "POST":
        form = LancamentoForm(request.POST, **kwargs)
        if form.is_valid():
            try:
                criar_lancamento(request.user, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                if form.cleaned_data["origem"] == "CARTAO":
                    periodo_destino = form.cleaned_data["ciclo"]
                elif form.cleaned_data["situacao"] == Situacao.PREVISTO:
                    periodo_destino = form.cleaned_data["vencimento"].strftime("%Y-%m")
                else:
                    periodo_destino = form.cleaned_data["data"].strftime("%Y-%m")
                if form.ciclo_aviso:
                    messages.warning(request, form.ciclo_aviso)
                messages.success(request, "Lançamento salvo e indicadores atualizados.")
                return redirect(_url_retorno_lancamento(request, periodo_destino, "dashboard"))
    else:
        form = LancamentoForm(initial=clone_initial, **kwargs)
    titulo = "Clonar lançamento" if clone_evento else "Novo lançamento"
    return render(request, "financeiro/form.html", {
        "form": form,
        "titulo": titulo,
        "formulario_lancamento": True,
        "ciclo_aviso": form.ciclo_aviso,
    })


def dados_clonagem_lancamento(evento):
    compra = evento.compras_cartao.select_related("cartao").prefetch_related(
        "parcelas__fatura", "parcelas__categoria", "parcelas__pessoa"
    ).first()
    if compra:
        parcela = compra.parcelas.order_by("numero", "id").first()
        rateio = evento.rateios.first()
        return {
            "descricao": parcela.descricao or evento.descricao,
            "natureza": parcela.natureza or evento.natureza,
            "data": None,
            "valor": parcela.valor,
            "origem": "CARTAO",
            "conta": None,
            "cartao": compra.cartao,
            "categoria": parcela.categoria or (rateio.categoria if rateio else None),
            "pessoa": parcela.pessoa or evento.pessoa,
            "pessoa_nome_livre": parcela.pessoa_nome_livre or evento.pessoa_nome_livre,
            "ambito": parcela.ambito or evento.ambito,
            "situacao": parcela.situacao,
            "vencimento": None,
            "ciclo": parcela.fatura.ciclo,
            "quantidade_parcelas": 1,
            "observacao": evento.observacao,
        }
    iniciais = dados_edicao_lancamento(evento.usuario, evento)
    iniciais["data"] = None
    iniciais["vencimento"] = None
    return iniciais


@login_required
def lancamento_clonar(request, pk):
    evento = get_object_or_404(EventoFinanceiro, pk=pk, usuario=request.user)
    parametros = {
        "clone_evento": evento.pk,
        "period": request.GET.get("period", ""),
        "return_to": request.GET.get("return_to", "eventos"),
    }
    for nome in ("account", "card"):
        valor = request.GET.get(nome)
        if valor and valor.isdigit():
            parametros[nome] = valor
    if request.GET.get("group_card_invoices") == "1":
        parametros["group_card_invoices"] = "1"
    return redirect(f"{reverse('evento_novo')}?{urlencode(parametros)}")


@login_required
def lancamento_editar(request, pk):
    evento = get_object_or_404(EventoFinanceiro, pk=pk, usuario=request.user)
    if evento.compras_cartao.exists():
        parcela = evento.compras_cartao.first().parcelas.order_by("numero", "id").first()
        if parcela:
            return redirect("parcela_cartao_editar", pk=parcela.pk)
    iniciais = dados_edicao_lancamento(request.user, evento)
    possui_liquidacao = Liquidacao.objects.filter(
        movimento_conta__evento=evento,
        status=Liquidacao.Status.ATIVA,
    ).exists()
    protegido = lancamento_possui_dados_protegidos(evento) or possui_liquidacao
    kwargs = {
        "usuario": request.user,
        "evento": evento,
        "bloquear_financeiro": protegido,
        "initial": iniciais,
    }
    if request.method == "POST":
        form = LancamentoForm(request.POST, **kwargs)
        if form.is_valid():
            try:
                evento = editar_lancamento_conta(request.user, evento.pk, form.cleaned_data)
                if form.cleaned_data.get("aplicar_recorrencia") == "FUTUROS":
                    replicar_edicao_recorrencia(request.user, evento, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                periodo_destino = (
                    form.cleaned_data["vencimento"].strftime("%Y-%m")
                    if form.cleaned_data["situacao"] == Situacao.PREVISTO
                    else form.cleaned_data["data"].strftime("%Y-%m")
                )
                if form.ciclo_aviso:
                    messages.warning(request, form.ciclo_aviso)
                messages.success(request, "Lançamento atualizado; vínculos financeiros preservados.")
                return redirect(_url_retorno_lancamento(request, periodo_destino))
    else:
        form = LancamentoForm(**kwargs)
    return render(request, "financeiro/form.html", {
        "form": form,
        "titulo": "Editar lançamento",
        "formulario_lancamento": True,
        "edicao_lancamento": True,
        "edicao_protegida": protegido,
        "ciclo_aviso": form.ciclo_aviso,
    })


@login_required
def cartoes_faturas(request):
    contexto = consultar_cartoes_faturas(
        request.user,
        ciclo=request.GET.get("cycle"),
        conta_id=request.GET.get("account"),
        cartao_id=request.GET.get("card"),
        fatura_id=request.GET.get("invoice"),
    )
    return render(request, "financeiro/cartoes_faturas.html", contexto)


def _retorno_fatura(fatura):
    return redirect(f"{reverse('cartoes_faturas')}?cycle={fatura.ciclo}&card={fatura.cartao_id}&invoice={fatura.pk}")


def _formulario_fatura(request, form, titulo):
    return render(request, "financeiro/form.html", {"form": form, "titulo": titulo})


@login_required
def fatura_fechar(request, pk):
    fatura = get_object_or_404(Fatura.objects.select_related("cartao__conta_pagamento_padrao"), pk=pk, usuario=request.user)
    form = FechamentoFaturaForm(request.POST or None, usuario=request.user, fatura=fatura)
    if request.method == "POST" and form.is_valid():
        try:
            fechar_fatura(request.user, fatura.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Fatura fechada; o título a pagar foi atualizado.")
            return _retorno_fatura(fatura)
    return _formulario_fatura(request, form, "Conferir e fechar fatura")


@login_required
def fatura_programar_pagamento(request, pk):
    titulo = get_object_or_404(Titulo.objects.select_related("fatura"), pk=pk, usuario=request.user, fatura__isnull=False)
    form = ProgramacaoPagamentoForm(request.POST or None, usuario=request.user, titulo=titulo)
    if request.method == "POST" and form.is_valid():
        try:
            programar_pagamento(
                request.user, titulo.pk, form.cleaned_data["conta"], form.cleaned_data["data_programada"],
                form.cleaned_data["valor"], chave=request.POST.get("idempotency_key") or str(uuid4()),
                observacao=form.cleaned_data["observacao"],
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Pagamento programado sem movimentar a conta.")
            return _retorno_fatura(titulo.fatura)
    return _formulario_fatura(request, form, "Programar pagamento")


@login_required
def fatura_conciliar_pagamento(request, pk):
    titulo = get_object_or_404(Titulo.objects.select_related("fatura"), pk=pk, usuario=request.user, fatura__isnull=False)
    form = ConciliacaoPagamentoForm(request.POST or None, usuario=request.user, titulo=titulo)
    if request.method == "POST" and form.is_valid():
        try:
            conciliar_pagamento(request.user, titulo.pk, form.cleaned_data["movimento"].pk, form.cleaned_data.get("valor"))
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Débito existente conciliado com a fatura.")
            return _retorno_fatura(titulo.fatura)
    return _formulario_fatura(request, form, "Conciliar pagamento")


@login_required
def fatura_pagamento_manual(request, pk):
    titulo = get_object_or_404(Titulo.objects.select_related("fatura"), pk=pk, usuario=request.user, fatura__isnull=False)
    form = PagamentoManualFaturaForm(request.POST or None, usuario=request.user, titulo=titulo)
    if request.method == "POST" and form.is_valid():
        try:
            registrar_pagamento_manual(
                request.user, titulo.pk, form.cleaned_data["conta"], form.cleaned_data["data_pagamento"],
                form.cleaned_data["valor"], request.POST.get("idempotency_key") or str(uuid4()), form.cleaned_data["observacao"],
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Pagamento manual registrado e liquidado.")
            return _retorno_fatura(titulo.fatura)
    return _formulario_fatura(request, form, "Registrar pagamento manual")


@login_required
def fatura_transportar_saldo(request, pk):
    titulo = get_object_or_404(Titulo.objects.select_related("fatura__cartao"), pk=pk, usuario=request.user, fatura__isnull=False)
    form = TransporteSaldoFaturaForm(request.POST or None, usuario=request.user, titulo=titulo)
    if request.method == "POST" and form.is_valid():
        try:
            criar_transporte(
                request.user, titulo.pk, form.cleaned_data["fatura_destino"].pk, form.cleaned_data["valor"],
                form.cleaned_data["data_identificacao"], chave=request.POST.get("idempotency_key") or str(uuid4()),
                observacao=form.cleaned_data["observacao"],
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Saldo transportado e registrado no histórico das duas faturas.")
            return _retorno_fatura(titulo.fatura)
    return _formulario_fatura(request, form, "Transportar saldo")


@login_required
def fatura_reabrir(request, pk):
    fatura = get_object_or_404(Fatura, pk=pk, usuario=request.user)
    form = ReaberturaFaturaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            reabrir_fatura(request.user, fatura.pk, form.cleaned_data["motivo"])
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, "Fatura reaberta ou encaminhada para correção.")
            return _retorno_fatura(fatura)
    return _formulario_fatura(request, form, "Reabrir ou corrigir fatura")


@login_required
def parcelas_futuras(request):
    contexto = consultar_parcelas_futuras(
        request.user,
        ciclo=request.GET.get("cycle"),
        conta_id=request.GET.get("account"),
        cartao_id=request.GET.get("card"),
    )
    return render(request, "financeiro/parcelas_futuras.html", contexto)


@login_required
def compra_cartao_nova(request):
    ciclo = request.GET.get("cycle")
    cartao_preferido = Cartao.objects.filter(
        pk=request.GET.get("card"),
        usuario=request.user,
        ativo=True,
    ).first()
    if request.method == "POST":
        form = CompraCartaoForm(request.POST, usuario=request.user)
        if form.is_valid():
            try:
                if form.cleaned_data.get("modo_lancamento") == "RECORRENTE":
                    dados = dict(form.cleaned_data)
                    dados.update({
                        "origem": "CARTAO",
                        "data": dados.pop("data_original"),
                        "vencimento": None,
                    })
                    evento = criar_lancamento(request.user, dados)
                    compra = evento.compras_cartao.get()
                else:
                    compra = criar_compra_cartao(request.user, form.cleaned_data)
            except (ValidationError, Cartao.DoesNotExist) as exc:
                mensagem = exc.messages[0] if isinstance(exc, ValidationError) else "O cartão selecionado não está disponível."
                form.add_error(None, mensagem)
            else:
                if form.ciclo_aviso:
                    messages.warning(request, form.ciclo_aviso)
                messages.success(request, "Compra registrada e parcelas projetadas com sucesso.")
                return redirect(
                    f"{reverse('cartoes_faturas')}?cycle={form.cleaned_data['ciclo']}&card={compra.cartao_id}"
                )
    else:
        form = CompraCartaoForm(
            usuario=request.user,
            cartao_preferido=cartao_preferido,
            ciclo=ciclo,
        )
    return render(request, "financeiro/form.html", {
        "form": form,
        "titulo": "Nova compra",
        "formulario_lancamento": True,
        "ciclo_aviso": form.ciclo_aviso,
    })


@login_required
def parcela_cartao_editar(request, pk):
    parcela = get_object_or_404(
        ParcelaCartao.objects.select_related(
            "compra__evento",
            "fatura__cartao",
            "categoria",
            "pessoa",
        ),
        pk=pk,
        compra__usuario=request.user,
    )
    if request.method == "POST":
        form = CompraCartaoForm(request.POST, usuario=request.user, parcela=parcela)
        if form.is_valid():
            try:
                parcela = editar_parcela_cartao(request.user, parcela.pk, form.cleaned_data)
                if form.cleaned_data.get("aplicar_recorrencia") == "FUTUROS":
                    replicar_edicao_recorrencia(request.user, parcela.compra.evento, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                if form.ciclo_aviso:
                    messages.warning(request, form.ciclo_aviso)
                messages.success(request, "Item da fatura atualizado; as demais parcelas foram preservadas.")
                if request.GET.get("return_to") == "eventos":
                    return redirect(_url_retorno_lancamento(request, parcela.fatura.ciclo))
                return redirect(
                    f"{reverse('cartoes_faturas')}?cycle={parcela.fatura.ciclo}&card={parcela.fatura.cartao_id}"
                )
    else:
        form = CompraCartaoForm(usuario=request.user, parcela=parcela)
    return render(request, "financeiro/form.html", {
        "form": form,
        "titulo": "Editar lançamento",
        "formulario_lancamento": True,
        "edicao_lancamento": True,
        "ciclo_aviso": form.ciclo_aviso,
    })


class ContaListView(UsuarioMixin, ListView):
    model = Conta
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"

    def get_queryset(self):
        queryset = super().get_queryset()
        return filtrar_cadastro(queryset, self.request)

    def get_context_data(self, **kwargs):
        return cadastro_context(super().get_context_data(**kwargs), self.request, "Contas financeiras", "conta_nova", "conta")


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

    def form_valid(self, form):
        conta_anterior = self.get_object()
        saldo_anterior = (conta_anterior.saldo_inicial, conta_anterior.data_saldo_inicial)
        with transaction.atomic():
            resposta = super().form_valid(form)
            saldo_atual = (self.object.saldo_inicial, self.object.data_saldo_inicial)
            if saldo_anterior != saldo_atual:
                reprocessar_saldo_conta(self.object.pk)
        return resposta


class CartaoListView(UsuarioMixin, ListView):
    model = Cartao
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    def get_queryset(self):
        queryset = super().get_queryset()
        return filtrar_cadastro(queryset, self.request, active_field="ativo")

    def get_context_data(self, **kwargs):
        return cadastro_context(super().get_context_data(**kwargs), self.request, "Cadastro de cartões", "cartao_novo", "cartao")


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

    def form_valid(self, form):
        dia_anterior = self.get_object().dia_vencimento
        with transaction.atomic():
            resposta = super().form_valid(form)
            if dia_anterior != self.object.dia_vencimento:
                sincronizar_vencimentos_faturas_abertas_cartao(self.object)
        return resposta


class CategoriaListView(UsuarioMixin, ListView):
    model = Categoria
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    def get_queryset(self):
        queryset = super().get_queryset().select_related("categoria_pai")
        return filtrar_cadastro(queryset, self.request)

    def get_context_data(self, **kwargs):
        return cadastro_context(super().get_context_data(**kwargs), self.request, "Categorias", "categoria_nova", "categoria")


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
    def get_queryset(self):
        queryset = super().get_queryset()
        return filtrar_cadastro(queryset, self.request)

    def get_context_data(self, **kwargs):
        return cadastro_context(super().get_context_data(**kwargs), self.request, "Pessoas", "pessoa_nova", "pessoa")


class PessoaCreateView(UsuarioMixin, CreateView):
    model = Pessoa
    form_class = PessoaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("pessoas")
    extra_context = {"titulo": "Nova pessoa"}


class PessoaUpdateView(UsuarioMixin, UpdateView):
    model = Pessoa
    form_class = PessoaForm
    template_name = "financeiro/form.html"
    success_url = reverse_lazy("pessoas")
    extra_context = {"titulo": "Editar pessoa"}


@login_required
def importar_ofx(request):
    if request.method == "POST":
        form = ImportacaoOFXForm(request.POST, request.FILES, usuario=request.user)
        if form.is_valid():
            arquivo = form.cleaned_data["arquivo_ofx"]
            conteudo = arquivo.read()
            arquivo.seek(0)
            try:
                documento = OFXParser.parse(conteudo)
            except OFXError as exc:
                form.add_error("arquivo_ofx", str(exc))
            else:
                if documento.origem != form.cleaned_data["origem"]:
                    detectada = "cartão" if documento.origem == Importacao.Origem.CARTAO else "conta corrente"
                    form.add_error("origem", f"O conteúdo foi identificado como OFX de {detectada}.")
                else:
                    with transaction.atomic():
                        importacao = form.save(commit=False)
                        importacao.instituicao = documento.instituicao or documento.banco
                        importacao.identificador_conta = documento.identificador_conta
                        importacao.data_inicio = documento.data_inicio
                        importacao.data_fim = documento.data_fim
                        importacao.data_posicao = documento.data_posicao
                        importacao.saldo_informado = documento.saldo
                        importacao.total_debitos = sum((-item.valor for item in documento.transacoes if item.valor < 0), 0)
                        importacao.total_creditos = sum((item.valor for item in documento.transacoes if item.valor > 0), 0)
                        importacao.total_liquido = sum((item.valor for item in documento.transacoes), 0)
                        importacao.adaptador = "conta_ofx" if documento.origem == Importacao.Origem.CONTA else "cartao_ofx"
                        importacao.versao_adaptador = "1.0"
                        importacao.save()
                        criar_itens(importacao, documento)
                    messages.success(request, "Arquivo processado. Revise a conciliação antes de confirmar.")
                    return redirect("importacao_revisao", pk=importacao.pk)
    else:
        form = ImportacaoOFXForm(usuario=request.user)
    if request.method == "POST" and form.errors:
        mensagens_exibidas = set()
        for erros in form.errors.values():
            for erro in erros:
                texto = str(erro)
                if texto not in mensagens_exibidas:
                    messages.error(request, texto)
                    mensagens_exibidas.add(texto)
    importacoes = Importacao.objects.filter(usuario=request.user).select_related("conta", "cartao")[:7]
    return render(
        request,
        "financeiro/importar.html",
        {
            "form": form,
            "form_planilha": ImportacaoPlanilhaForm(usuario=request.user),
            "importacoes": importacoes,
        },
    )


@login_required
def importar_planilha(request):
    form = ImportacaoPlanilhaForm(request.POST or None, request.FILES or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            compras = ler_compras_planilha(form.cleaned_data["arquivo_planilha"], request.user)
            with transaction.atomic():
                importacao = form.save(commit=False)
                importacao.data_inicio = min(compra["data_compra"] for compra in compras)
                importacao.data_fim = max(compra["data_compra"] for compra in compras)
                importacao.total_debitos = sum((compra["valor_total"] for compra in compras), Decimal("0.00"))
                importacao.total_creditos = Decimal("0.00")
                importacao.total_liquido = -importacao.total_debitos
                importacao.save()
                criar_itens_planilha(importacao, compras)
        except ValidationError as exc:
            mensagem = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            form.add_error("arquivo_planilha", mensagem)
        else:
            messages.success(request, "Planilha processada. Revise as compras futuras antes de confirmar.")
            return redirect("importacao_revisao", pk=importacao.pk)
    if request.method == "POST" and form.errors:
        mensagens_exibidas = set()
        for erros in form.errors.values():
            for erro in erros:
                texto = str(erro)
                if texto not in mensagens_exibidas:
                    messages.error(request, texto)
                    mensagens_exibidas.add(texto)
    importacoes = Importacao.objects.filter(usuario=request.user).select_related("conta", "cartao")[:20]
    return render(
        request,
        "financeiro/importar.html",
        {
            "form": ImportacaoOFXForm(usuario=request.user),
            "form_planilha": form,
            "importacoes": importacoes,
        },
    )


@login_required
@require_GET
def baixar_modelo_planilha(request):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="modelo_compras_cartao.csv"'
    resposta.write("\ufeffdescricao;data_compra;valor_total;quantidade_parcelas;categoria;pessoa;ambito;observacao\n")
    resposta.write("Exemplo de assinatura;15/10/2026;49,90;1;;;PESSOAL;\n")
    return resposta


@login_required
def importacao_revisao(request, pk):
    importacao = get_object_or_404(Importacao.objects.select_related("conta", "cartao"), usuario=request.user, pk=pk)
    if request.method == "POST":
        if importacao.status != Importacao.Status.EM_REVISAO:
            messages.error(request, "Este lote não está mais disponível para edição.")
            return redirect("importacao_resultado", pk=importacao.pk)
        item = get_object_or_404(ItemImportacao, pk=request.POST.get("item_id"), importacao=importacao)
        form_item = ItemImportacaoForm(request.POST, instance=item, usuario=request.user)
        if form_item.is_valid():
            try:
                with transaction.atomic():
                    item = form_item.save(commit=False)
                    selecionar_vinculo_item(
                        item,
                        request.user,
                        titulo_id=form_item.cleaned_data.get("titulo_alvo_id"),
                        titulos_ids=form_item.cleaned_data.get("titulos_alvo_ids"),
                        movimento_id=form_item.cleaned_data.get("movimento_alvo_id"),
                        parcela_id=form_item.cleaned_data.get("parcela_alvo_id"),
                    )
                    atualizar_status_revisao(item)
                    item.save()
                    sincronizar_titulos_multiplos(item, getattr(item, "_titulos_multiplos_ids", []))
            except ValidationError as exc:
                form_item.add_error("acao", exc.messages[0])
            else:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    resumo_atualizado = resumo_importacao(importacao)
                    return JsonResponse(
                        {
                            "ok": True,
                            "message": "Item da importação atualizado.",
                            "item": {
                                "id": item.pk,
                                "status": item.status,
                                "status_display": item.get_status_display(),
                                "motivo": item.motivo_status or "Novo registro identificado.",
                                "revisado": item.revisado_em is not None,
                                "aviso_ciclo": aviso_ciclo_cartao(
                                    importacao.cartao,
                                    item.data_final,
                                    importacao.ciclo,
                                    numero_parcela=item.numero_parcela,
                                    total_parcelas=item.total_parcelas,
                                ),
                            },
                            "contagens": resumo_atualizado["contagens"],
                            "titulos_multiplos": {
                                "quantidade": item.titulos_multiplos.count(),
                                "total": str(sum((vinculo.valor for vinculo in item.titulos_multiplos.all()), Decimal("0.00"))),
                            },
                        }
                    )
                messages.success(request, "Item da importação atualizado.")
                return redirect("importacao_revisao", pk=importacao.pk)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            erros = [str(erro) for lista in form_item.errors.values() for erro in lista]
            return JsonResponse(
                {"ok": False, "message": erros[0] if erros else "Revise os campos informados no item.", "errors": erros},
                status=422,
            )
        messages.error(request, "Revise os campos informados no item.")
    status = request.GET.get("status", "")
    revisao = request.GET.get("revisao", "")
    busca = request.GET.get("q", "").strip()
    itens = importacao.itens.select_related(
        "categoria",
        "pessoa",
        "evento",
        "movimento_conta__evento",
        "titulo_alvo__conta",
        "parcela__compra__evento",
        "parcela__fatura__cartao",
    ).prefetch_related(
        Prefetch("titulos_multiplos", queryset=VinculoTituloImportacao.objects.select_related("titulo__conta"))
    )
    if status:
        itens = itens.filter(status=status)
    if revisao == "REVISADOS":
        itens = itens.filter(revisado_em__isnull=False)
    elif revisao == "NAO_REVISADOS":
        itens = itens.filter(revisado_em__isnull=True)
    if busca:
        itens = itens.filter(Q(descricao_original__icontains=busca) | Q(identificador_externo__icontains=busca))
    itens = list(itens)
    for item in itens:
        item.titulos_multiplos_lista = list(item.titulos_multiplos.all())
        item.aviso_ciclo = aviso_ciclo_cartao(
            importacao.cartao,
            item.data_final,
            importacao.ciclo,
            numero_parcela=item.numero_parcela,
            total_parcelas=item.total_parcelas,
        )
    contexto = {
        "importacao": importacao,
        "itens": itens,
        "resumo": resumo_importacao(importacao),
        "busca": busca,
        "status_filtro": status,
        "revisao_filtro": revisao,
        "categorias": Categoria.objects.filter(usuario=request.user, ativa=True).select_related("categoria_pai"),
        "pessoas": Pessoa.objects.filter(usuario=request.user, ativa=True),
        "naturezas": EventoFinanceiro._meta.get_field("natureza").choices,
        "ambitos": EventoFinanceiro._meta.get_field("ambito").choices,
        "acoes": ItemImportacao.Acao.choices,
        "form_lote": AplicacaoLoteForm(usuario=request.user),
    }
    return render(request, "financeiro/importacao_revisao.html", contexto)


@login_required
@require_GET
def importacao_candidatos_vinculo(request, pk, item_id):
    importacao = get_object_or_404(
        Importacao.objects.select_related("conta", "cartao"),
        usuario=request.user,
        pk=pk,
        status=Importacao.Status.EM_REVISAO,
    )
    item = get_object_or_404(
        ItemImportacao.objects.select_related("importacao", "categoria"),
        pk=item_id,
        importacao=importacao,
    )
    try:
        resultado = buscar_candidatos_vinculo(
            item,
            request.user,
            tipo=request.GET.get("tipo", "TODOS"),
            busca=request.GET.get("q", ""),
            escopo=request.GET.get("escopo", "SUGESTOES"),
            pagina=request.GET.get("pagina", 1),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        mensagem = exc.messages[0] if isinstance(exc, ValidationError) else "Parâmetros de busca inválidos."
        return JsonResponse({"ok": False, "message": mensagem}, status=422)
    return JsonResponse({"ok": True, **resultado})


@login_required
@require_POST
def importacao_aplicar_lote(request, pk):
    importacao = get_object_or_404(Importacao, usuario=request.user, pk=pk, status=Importacao.Status.EM_REVISAO)
    itens_selecionados = request.POST.getlist("itens_selecionados")
    form = AplicacaoLoteForm(request.POST, usuario=request.user, itens_selecionados=itens_selecionados)
    if form.is_valid():
        try:
            resultado = aplicar_alteracoes_lote(importacao.pk, request.user, form.cleaned_data, itens_selecionados)
        except ValidationError as exc:
            erros = exc.messages
        else:
            itens = resultado["itens"]
            quantidade_preservada = resultado["quantidade_preservada"]
            mensagem = f"Classificação aplicada a {len(itens)} item(ns)."
            if quantidade_preservada:
                mensagem += (
                    " 1 item já revisado foi preservado."
                    if quantidade_preservada == 1
                    else f" {quantidade_preservada} itens já revisados foram preservados."
                )
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": True,
                        "message": mensagem,
                        "items": [
                            {
                                "id": item.pk,
                                "status": item.status,
                                "status_display": item.get_status_display(),
                                "motivo": item.motivo_status or "Novo registro identificado.",
                                "categoria": item.categoria_id or "",
                                "pessoa": item.pessoa_id or "",
                                "ambito": item.ambito,
                                "acao": item.acao,
                                "observacao": item.observacao,
                                "revisado": item.revisado_em is not None,
                            }
                            for item in itens
                        ],
                        "quantidade_preservada": quantidade_preservada,
                        "contagens": resumo_importacao(importacao)["contagens"],
                    }
                )
            messages.success(request, mensagem)
            return redirect("importacao_revisao", pk=importacao.pk)
    else:
        erros = [str(erro) for lista in form.errors.values() for erro in lista]
    mensagem = erros[0] if erros else "Revise os dados da classificação em lote."
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": False, "message": mensagem, "errors": erros}, status=422)
    messages.error(request, mensagem)
    return redirect("importacao_revisao", pk=importacao.pk)


@login_required
@require_POST
def importacao_confirmar(request, pk):
    try:
        importacao = confirmar_importacao(pk, request.user)
    except (Importacao.DoesNotExist, ValidationError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Importação não encontrada.")
        return redirect("importacao_revisao", pk=pk)
    messages.success(request, "Importação confirmada sem duplicar lançamentos conciliados.")
    return redirect("importacao_resultado", pk=importacao.pk)


@login_required
@require_POST
def importacao_excluir(request, pk):
    importacao = get_object_or_404(
        Importacao,
        usuario=request.user,
        pk=pk,
        status=Importacao.Status.EM_REVISAO,
    )
    nome_arquivo = importacao.arquivo.name
    armazenamento = importacao.arquivo.storage
    with transaction.atomic():
        importacao.delete()
        if nome_arquivo:
            transaction.on_commit(lambda: armazenamento.delete(nome_arquivo))
    messages.success(request, "Lote em revisão excluído com sucesso.")
    return redirect("importar_ofx")


@login_required
@require_POST
def importacao_desfazer(request, pk):
    try:
        importacao = desfazer_importacao(pk, request.user)
    except (Importacao.DoesNotExist, ValidationError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Importação não encontrada.")
        return redirect("importacao_resultado", pk=pk)
    messages.success(request, "Importação desfeita; o histórico do lote foi preservado.")
    return redirect("importacao_resultado", pk=importacao.pk)


@login_required
def importacao_resultado(request, pk):
    importacao = get_object_or_404(Importacao.objects.select_related("conta", "cartao"), usuario=request.user, pk=pk)
    return render(
        request,
        "financeiro/importacao_resultado.html",
        {"importacao": importacao, "resumo": resumo_importacao(importacao), "itens": importacao.itens.select_related("evento", "parcela")},
    )


@login_required
def placeholder(request, titulo):
    return render(request, "financeiro/placeholder.html", {"titulo": titulo})


def filtrar_cadastro(queryset, request, active_field="ativa"):
    termo = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    if termo:
        queryset = queryset.filter(Q(nome__icontains=termo))
    if status == "active":
        queryset = queryset.filter(**{active_field: True})
    elif status == "inactive":
        queryset = queryset.filter(**{active_field: False})
    return queryset


def cadastro_context(context, request, titulo, novo_url, tipo):
    context.update(
        {
            "titulo": titulo,
            "novo_url": novo_url,
            "tipo_cadastro": tipo,
            "busca": request.GET.get("q", ""),
            "status_filtro": request.GET.get("status", "all"),
        }
    )
    return context


def cadastro_modelo(tipo):
    return {
        "conta": (Conta, "ativa", "contas"),
        "cartao": (Cartao, "ativo", "cartoes"),
        "categoria": (Categoria, "ativa", "categorias"),
        "pessoa": (Pessoa, "ativa", "pessoas"),
    }[tipo]


@login_required
@require_POST
def alternar_cadastro(request, tipo, pk):
    model, active_field, redirect_name = cadastro_modelo(tipo)
    objeto = get_object_or_404(model, pk=pk, usuario=request.user)
    atual = getattr(objeto, active_field)
    setattr(objeto, active_field, not atual)
    objeto.save(update_fields=[active_field, "atualizado_em"])
    messages.success(request, "Cadastro ativado." if atual is False else "Cadastro inativado; histórico preservado.")
    return redirect(redirect_name)


@login_required
@require_POST
def reprocessar_saldo_conta_view(request, pk):
    conta = get_object_or_404(Conta, pk=pk, usuario=request.user)
    with transaction.atomic():
        resultado = reprocessar_saldo_conta(conta.pk)
    messages.success(
        request,
        f"Saldo da conta reprocessado: {resultado['quantidade_periodos']} ciclo(s) e "
        f"{resultado['quantidade_movimentos']} movimento(s) considerados.",
    )
    return redirect("contas")


@login_required
@require_POST
def excluir_cadastro(request, tipo, pk):
    model, _active_field, redirect_name = cadastro_modelo(tipo)
    objeto = get_object_or_404(model, pk=pk, usuario=request.user)
    try:
        objeto.delete()
        messages.success(request, "Registro excluído.")
    except ProtectedError:
        if tipo == "categoria":
            messages.error(request, "A categoria possui movimentações ou categorias vinculadas e deve ser inativada.")
        else:
            messages.error(request, "Há vínculos com este cadastro. Use Inativar para preservar o histórico.")
    return redirect(redirect_name)


@login_required
@require_POST
def excluir_evento(request, pk):
    try:
        excluidos = excluir_lancamento_conta(
            request.user,
            pk,
            excluir_futuros=request.POST.get("excluir_futuros") == "1",
        )
        messages.success(request, f"Lançamento excluído.{f' {excluidos} lançamento(s) futuro(s) previsto(s) também foram excluídos.' if excluidos else ''}")
    except (ValidationError, ProtectedError, EventoFinanceiro.DoesNotExist) as exc:
        mensagem = exc.messages[0] if isinstance(exc, ValidationError) else "Há vínculos com este lançamento. Revise os vínculos antes de excluir."
        messages.error(request, mensagem)
    periodo = request.GET.get("period") or request.POST.get("period")
    return redirect(_url_retorno_lancamento(request, periodo or "", "eventos") if periodo else "eventos")


@login_required
@require_POST
def excluir_parcela_evento(request, pk):
    try:
        excluidos = excluir_parcela_lancamento(
            request.user,
            pk,
            excluir_futuros=request.POST.get("excluir_futuros") == "1",
        )
        messages.success(request, f"Parcela excluída e fatura recalculada.{f' {excluidos} lançamento(s) futuro(s) previsto(s) também foram excluídos.' if excluidos else ''}")
    except (ValidationError, ProtectedError, ParcelaCartao.DoesNotExist) as exc:
        mensagem = exc.messages[0] if isinstance(exc, ValidationError) else "Há vínculos com esta parcela. Revise a fatura antes de excluir."
        messages.error(request, mensagem)
    periodo = request.GET.get("period") or request.POST.get("period")
    return redirect(_url_retorno_lancamento(request, periodo or "", "eventos") if periodo else "eventos")
