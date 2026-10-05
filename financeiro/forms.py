import hashlib

from django import forms

from .models import Cartao, Categoria, Conta, EventoFinanceiro, Importacao, NaturezaEvento, Pessoa


class ContaForm(forms.ModelForm):
    class Meta:
        model = Conta
        fields = [
            "nome",
            "banco",
            "agencia",
            "numero",
            "titular",
            "tipo",
            "ambito",
            "saldo_inicial",
            "data_saldo_inicial",
            "limite_credito",
            "ativa",
        ]
        widgets = {"data_saldo_inicial": forms.DateInput(attrs={"type": "date"})}


class CartaoForm(forms.ModelForm):
    class Meta:
        model = Cartao
        fields = [
            "nome",
            "emissor",
            "identificador_externo",
            "final",
            "dia_fechamento",
            "dia_vencimento",
            "conta_pagamento_padrao",
            "limite",
            "ativo",
        ]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario:
            self.fields["conta_pagamento_padrao"].queryset = Conta.objects.filter(usuario=usuario)


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "tipo", "categoria_pai", "ativa"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario:
            queryset = Categoria.objects.filter(usuario=usuario)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            self.fields["categoria_pai"].queryset = queryset


class PessoaForm(forms.ModelForm):
    class Meta:
        model = Pessoa
        fields = ["nome", "documento", "observacao", "ativa"]


class EventoFinanceiroForm(forms.ModelForm):
    class Meta:
        model = EventoFinanceiro
        fields = ["natureza", "descricao", "data", "vencimento", "valor", "pessoa", "ambito", "situacao", "observacao"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "vencimento": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario:
            self.fields["pessoa"].queryset = Pessoa.objects.filter(usuario=usuario)

    def clean(self):
        cleaned = super().clean()
        natureza = cleaned.get("natureza")
        valor = cleaned.get("valor")
        if natureza in {NaturezaEvento.DESPESA, NaturezaEvento.PAGAMENTO_FATURA} and valor and valor < 0:
            self.add_error("valor", "Informe despesas e pagamentos com valor positivo; o sinal fica no movimento de conta.")
        return cleaned


class ImportacaoOFXForm(forms.ModelForm):
    arquivo_ofx = forms.FileField(label="Arquivo OFX")

    class Meta:
        model = Importacao
        fields = ["origem", "conta", "cartao", "ciclo"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario:
            self.fields["conta"].queryset = Conta.objects.filter(usuario=usuario)
            self.fields["cartao"].queryset = Cartao.objects.filter(usuario=usuario)

    def clean_arquivo_ofx(self):
        arquivo = self.cleaned_data["arquivo_ofx"]
        if not arquivo.name.lower().endswith(".ofx"):
            raise forms.ValidationError("Envie um arquivo OFX.")
        return arquivo

    def save(self, commit=True):
        arquivo = self.cleaned_data["arquivo_ofx"]
        posicao = arquivo.tell()
        arquivo.seek(0)
        digest = hashlib.sha256(arquivo.read()).hexdigest()
        arquivo.seek(posicao)
        instance = super().save(commit=False)
        instance.usuario = self.usuario
        instance.arquivo = arquivo
        instance.nome_arquivo = arquivo.name
        instance.hash_arquivo = digest
        instance.status = Importacao.Status.EM_REVISAO
        if commit:
            instance.save()
        return instance
