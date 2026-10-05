from django.conf import settings
from django.db import models
from django.db.models import Q


class TimestampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Ambito(models.TextChoices):
    PESSOAL = "PESSOAL", "Pessoal"
    PROFISSIONAL = "PROFISSIONAL", "Profissional"
    NAO_DEFINIDO = "NAO_DEFINIDO", "Nao definido"


class Situacao(models.TextChoices):
    REALIZADO = "REALIZADO", "Realizado"
    PREVISTO = "PREVISTO", "Previsto"
    PENDENTE = "PENDENTE", "Pendente"


class NaturezaEvento(models.TextChoices):
    DESPESA = "DESPESA", "Despesa"
    RECEITA = "RECEITA", "Receita"
    ESTORNO = "ESTORNO", "Estorno"
    PAGAMENTO_FATURA = "PAGAMENTO_FATURA", "Pagamento de fatura"
    TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"


class Conta(TimestampedModel):
    class Tipo(models.TextChoices):
        CORRENTE = "CORRENTE", "Conta corrente"
        POUPANCA = "POUPANCA", "Poupanca"
        CARTEIRA = "CARTEIRA", "Carteira"
        PAGAMENTO = "PAGAMENTO", "Conta de pagamento"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nome = models.CharField(max_length=120)
    banco = models.CharField(max_length=120, blank=True)
    agencia = models.CharField(max_length=30, blank=True)
    numero = models.CharField(max_length=60, blank=True)
    titular = models.CharField(max_length=160, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.CORRENTE)
    ambito = models.CharField(max_length=20, choices=Ambito.choices, default=Ambito.NAO_DEFINIDO)
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    data_saldo_inicial = models.DateField(null=True, blank=True)
    limite_credito = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["usuario", "ativa"]),
            models.Index(fields=["usuario", "banco", "numero"]),
        ]

    def __str__(self):
        return self.nome


class Pessoa(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nome = models.CharField(max_length=160)
    documento = models.CharField(max_length=40, blank=True)
    observacao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nome"], name="uniq_pessoa_usuario_nome"),
        ]

    def __str__(self):
        return self.nome


class Categoria(TimestampedModel):
    class Tipo(models.TextChoices):
        DESPESA = "DESPESA", "Despesa"
        RECEITA = "RECEITA", "Receita"
        AMBOS = "AMBOS", "Ambos"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.DESPESA)
    categoria_pai = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nome"], name="uniq_categoria_usuario_nome"),
        ]

    def __str__(self):
        return self.nome


class Cartao(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nome = models.CharField(max_length=120)
    emissor = models.CharField(max_length=120, blank=True)
    identificador_externo = models.CharField(max_length=80, blank=True)
    final = models.CharField(max_length=4, blank=True)
    dia_fechamento = models.PositiveSmallIntegerField(null=True, blank=True)
    dia_vencimento = models.PositiveSmallIntegerField(null=True, blank=True)
    conta_pagamento_padrao = models.ForeignKey(Conta, null=True, blank=True, on_delete=models.PROTECT)
    limite = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["usuario", "ativo"]),
            models.Index(fields=["usuario", "identificador_externo"]),
        ]

    def __str__(self):
        return self.nome


class Fatura(TimestampedModel):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        FECHADA = "FECHADA", "Fechada"
        PAGA = "PAGA", "Paga"
        PARCIAL = "PARCIAL", "Parcial"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cartao = models.ForeignKey(Cartao, on_delete=models.PROTECT)
    ciclo = models.CharField(max_length=7)
    fechamento = models.DateField(null=True, blank=True)
    vencimento = models.DateField(null=True, blank=True)
    total_bruto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_creditos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTA)

    class Meta:
        ordering = ["-ciclo", "cartao__nome"]
        constraints = [
            models.UniqueConstraint(fields=["cartao", "ciclo"], name="uniq_fatura_cartao_ciclo"),
        ]

    def __str__(self):
        return f"{self.cartao} {self.ciclo}"


class EventoFinanceiro(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    natureza = models.CharField(max_length=30, choices=NaturezaEvento.choices)
    descricao = models.CharField(max_length=220)
    data = models.DateField()
    vencimento = models.DateField(null=True, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    pessoa = models.ForeignKey(Pessoa, null=True, blank=True, on_delete=models.PROTECT)
    ambito = models.CharField(max_length=20, choices=Ambito.choices, default=Ambito.NAO_DEFINIDO)
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.REALIZADO)
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(fields=["usuario", "data"]),
            models.Index(fields=["usuario", "natureza", "situacao"]),
        ]

    def __str__(self):
        return self.descricao


class RateioCategoria(TimestampedModel):
    evento = models.ForeignKey(EventoFinanceiro, related_name="rateios", on_delete=models.CASCADE)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["evento", "categoria"], name="uniq_rateio_evento_categoria"),
        ]


class MovimentoConta(TimestampedModel):
    conta = models.ForeignKey(Conta, on_delete=models.PROTECT)
    evento = models.ForeignKey(EventoFinanceiro, related_name="movimentos_conta", on_delete=models.CASCADE)
    data_efetiva = models.DateField()
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    documento = models.CharField(max_length=80, blank=True)
    historico_original = models.TextField(blank=True)

    class Meta:
        ordering = ["-data_efetiva", "-id"]
        indexes = [
            models.Index(fields=["conta", "data_efetiva"]),
            models.Index(fields=["documento"]),
        ]


class CompraCartao(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cartao = models.ForeignKey(Cartao, on_delete=models.PROTECT)
    evento = models.ForeignKey(EventoFinanceiro, related_name="compras_cartao", on_delete=models.CASCADE)
    estabelecimento = models.CharField(max_length=180)
    data_compra = models.DateField()
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_parcelas = models.PositiveSmallIntegerField(default=1)
    chave_compra = models.CharField(max_length=120, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "cartao", "data_compra"]),
            models.Index(fields=["usuario", "chave_compra"]),
        ]


class ParcelaCartao(TimestampedModel):
    compra = models.ForeignKey(CompraCartao, related_name="parcelas", on_delete=models.CASCADE)
    fatura = models.ForeignKey(Fatura, related_name="parcelas", on_delete=models.PROTECT)
    numero = models.PositiveSmallIntegerField(default=1)
    total = models.PositiveSmallIntegerField(default=1)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.REALIZADO)

    class Meta:
        ordering = ["fatura__ciclo", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["compra", "numero"], name="uniq_parcela_compra_numero"),
        ]


class Titulo(TimestampedModel):
    class Tipo(models.TextChoices):
        RECEBER = "RECEBER", "Receber"
        PAGAR = "PAGAR", "Pagar"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descricao = models.CharField(max_length=220)
    vencimento = models.DateField()
    valor_original = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_aberto = models.DecimalField(max_digits=14, decimal_places=2)
    conta = models.ForeignKey(Conta, null=True, blank=True, on_delete=models.PROTECT)
    fatura = models.ForeignKey(Fatura, null=True, blank=True, on_delete=models.PROTECT)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["vencimento"]
        constraints = [
            models.UniqueConstraint(
                fields=["fatura"],
                condition=Q(ativo=True, fatura__isnull=False),
                name="uniq_titulo_ativo_por_fatura",
            ),
        ]


class Liquidacao(TimestampedModel):
    titulo = models.ForeignKey(Titulo, related_name="liquidacoes", on_delete=models.PROTECT)
    movimento_conta = models.ForeignKey(MovimentoConta, null=True, blank=True, on_delete=models.PROTECT)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data = models.DateField()
    observacao = models.TextField(blank=True)


class Importacao(TimestampedModel):
    class Origem(models.TextChoices):
        CONTA = "CONTA", "Conta corrente"
        CARTAO = "CARTAO", "Cartao"

    class Status(models.TextChoices):
        RECEBIDA = "RECEBIDA", "Recebida"
        EM_REVISAO = "EM_REVISAO", "Em revisao"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        DESFEITA = "DESFEITA", "Desfeita"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    arquivo = models.FileField(upload_to="importacoes/%Y/%m/")
    nome_arquivo = models.CharField(max_length=220)
    hash_arquivo = models.CharField(max_length=64)
    origem = models.CharField(max_length=20, choices=Origem.choices)
    instituicao = models.CharField(max_length=120, blank=True)
    conta = models.ForeignKey(Conta, null=True, blank=True, on_delete=models.PROTECT)
    cartao = models.ForeignKey(Cartao, null=True, blank=True, on_delete=models.PROTECT)
    ciclo = models.CharField(max_length=7, blank=True)
    adaptador = models.CharField(max_length=80, default="ofx")
    versao_adaptador = models.CharField(max_length=20, default="0.1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEBIDA)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "hash_arquivo"], name="uniq_importacao_usuario_hash"),
        ]

    def __str__(self):
        return self.nome_arquivo


class ItemImportacao(TimestampedModel):
    class Status(models.TextChoices):
        NOVO = "NOVO", "Novo"
        CONCILIADO = "CONCILIADO", "Conciliado"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        PENDENTE = "PENDENTE", "Pendente"

    importacao = models.ForeignKey(Importacao, related_name="itens", on_delete=models.CASCADE)
    identificador_externo = models.CharField(max_length=160, blank=True)
    ocorrencia = models.PositiveIntegerField(default=1)
    data = models.DateField(null=True, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    descricao_original = models.TextField(blank=True)
    registro_original = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    evento = models.ForeignKey(EventoFinanceiro, null=True, blank=True, on_delete=models.PROTECT)
    movimento_conta = models.ForeignKey(MovimentoConta, null=True, blank=True, on_delete=models.PROTECT)
    parcela = models.ForeignKey(ParcelaCartao, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["data", "id"]
        constraints = [
            models.UniqueConstraint(fields=["importacao", "identificador_externo", "ocorrencia"], name="uniq_item_importacao_ocorrencia"),
        ]


class RegraCategoria(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texto = models.CharField(max_length=160)
    pessoa = models.ForeignKey(Pessoa, null=True, blank=True, on_delete=models.PROTECT)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    ambito = models.CharField(max_length=20, choices=Ambito.choices, default=Ambito.NAO_DEFINIDO)
    ativa = models.BooleanField(default=True)


class Orcamento(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    mes = models.CharField(max_length=7)
    ambito = models.CharField(max_length=20, choices=Ambito.choices, default=Ambito.NAO_DEFINIDO)
    limite = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuario", "categoria", "mes", "ambito"], name="uniq_orcamento_categoria_mes_ambito"),
        ]
