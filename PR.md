# Iniciar MVP myfinanceiro

## Resumo

- Cria projeto Django `my_financeiro` com app `financeiro`.
- Configura PostgreSQL via `.env` e modo local `DJANGO_USE_SQLITE=True` para validacao sem tocar no banco remoto.
- Modela o nucleo financeiro inicial: contas, cartoes, categorias, pessoas, importacoes OFX, itens importados, eventos, movimentos, faturas, compras parceladas, titulos, liquidacoes, regras e orcamentos.
- Adiciona telas server-rendered para visao geral, lancamentos, cadastros e upload OFX.
- Implementa upload OFX em revisao, com hash do arquivo e itens pendentes para conciliacao.

## Regras contempladas

- OFX e o unico formato de importacao previsto no codigo inicial.
- Importacoes ficam em lote rastreavel, com hash e itens separados.
- Reimportacao tem base tecnica para anti-duplicidade por `usuario + hash_arquivo`.
- Fatura e unica por `cartao + ciclo`.
- Parcela e unica por `compra + numero`.
- Titulo ativo por fatura e restringido por constraint.
- Valores usam `DecimalField`, nao float.

## Validacao

Executado com `DJANGO_USE_SQLITE=True` para nao aplicar schema no PostgreSQL remoto:

```powershell
python manage.py check
python manage.py migrate --noinput
```

Resultado:

- `System check identified no issues (0 silenced).`
- `financeiro.0001_initial... OK`

## Proximos passos

- Implementar conciliacao completa dos itens OFX contra lancamentos/previsoes existentes.
- Confirmar lote importado em transacao.
- Adicionar fechamento/reabertura de fatura e baixa parcial de titulos.
- Criar testes automatizados para reimportacao, parcelas e pagamento de fatura.
