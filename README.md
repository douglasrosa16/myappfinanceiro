# myfinanceiro

MVP inicial do aplicativo financeiro descrito em `diagnostico-e-projeto-financeiro.md`, usando Django com paginas renderizadas no servidor e PostgreSQL.

## Escopo desta PR

- Projeto Django configurado para PostgreSQL.
- App `financeiro` com modelos iniciais para contas, cartoes, categorias, pessoas, importacoes OFX, eventos financeiros, movimentos de conta, faturas, compras parceladas, titulos, liquidacoes, regras e orcamentos.
- Migration inicial versionada.
- Telas server-rendered para visao geral, lancamentos, cadastros e upload OFX.
- Upload OFX em modo de revisao: calcula hash do arquivo, salva lote e cria itens pendentes para conciliacao posterior.
- Modo local `DJANGO_USE_SQLITE=True` para validar migrations sem tocar no banco remoto.

## Fora do escopo desta primeira PR

- Confirmacao definitiva de lotes OFX.
- Conciliacao automatica completa contra lancamentos existentes.
- Fechamento/reabertura operacional de faturas.
- Baixa parcial com recalculo automatico do saldo do titulo.
- Importadores Excel, TXT, CNAB 240 ou BANCOOB 500.

## Configuracao

Copie `.env.example` para `.env` e ajuste quando necessario.

```powershell
copy .env.example .env
```

As variaveis padrao apontam para o PostgreSQL informado:

```text
POSTGRES_HOST=100.127.41.45
POSTGRES_PORT=5432
POSTGRES_DB=myappfinanceiro
POSTGRES_USER=postgres
```

Preencha `POSTGRES_PASSWORD` apenas no arquivo `.env` local. Nao versione credenciais reais.

Para validar localmente sem aplicar nada no PostgreSQL remoto:

```powershell
$env:DJANGO_USE_SQLITE='True'
python manage.py migrate
python manage.py runserver
```

## Comandos de verificacao usados

```powershell
$env:DJANGO_USE_SQLITE='True'
python manage.py check
python manage.py migrate --noinput
```

Resultado: `System check identified no issues` e migration `financeiro.0001_initial` aplicada com sucesso em SQLite temporario.
