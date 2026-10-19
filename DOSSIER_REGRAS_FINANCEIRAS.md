# Dossiê de Regras Financeiras

**Versão da análise:** 19/10/2026
**Escopo:** retrato do código atual e registro das regras implementadas em dashboard, importação OFX/planilha, lançamentos, cartões, faturas e PWA.
**Status da validação:** análise estática complementada por `manage.py check`, 258 testes Django aprovados no ambiente virtual e consulta das migrations aplicadas. A seção 22 registra os resultados e as verificações de navegador, Docker e produção que continuam pendentes.

## 1. Objetivo do documento

Este documento consolida as regras financeiras identificadas no projeto Django `my-financeiro`. Ele distingue comportamento comprovado no código de comportamento parcial, não identificado, divergente ou recomendado. Não é uma especificação futura e não substitui os testes.

### Legenda de evidência

- **IMPLEMENTADO:** encontrado diretamente em código executável ou constraint.
- **PARCIAL:** existe, mas cobre apenas parte do cenário.
- **NÃO IDENTIFICADO:** não foi localizado código conclusivo.
- **DIVERGÊNCIA:** o comportamento atual difere da regra esperada/documentada.
- **RECOMENDAÇÃO:** melhoria sugerida; não está implementada.
- **CORRIGIDO:** risco ou divergência tratado pela implementação descrita neste documento.

## 2. Arquitetura relacionada ao domínio financeiro

### Stack e organização

- **Backend:** Django, ORM Django e templates server-rendered.
- **Banco:** PostgreSQL na configuração principal; SQLite pode ser selecionado por `DJANGO_USE_SQLITE=True` para validação local.
- **Frontend:** HTML/CSS/JavaScript embutido nos templates Django; não foi identificado um frontend React separado.
- **Aplicação:** projeto `my_financeiro`, app `financeiro`.
- **Camadas principais:** `financeiro/models.py` (persistência), `financeiro/forms.py` (entrada e validação), `financeiro/views.py`/`financeiro/urls.py` (HTTP), `financeiro/services/` (regras e consultas), `templates/` (apresentação), `financeiro/tests/` (Django TestCase).

### Fluxo geral

`template/formulário → view → service → ORM/repository implícito no service → banco`.

Não há uma camada `repository` nomeada; as consultas são feitas diretamente nos services e views. Os principais pontos são:

| Domínio | Arquivos principais |
|---|---|
| Contas e lançamentos | `financeiro/models.py`, `financeiro/services/lancamentos.py`, `financeiro/services/saldo_contas.py` |
| Cartões e faturas | `financeiro/services/cartoes_faturas.py`, `financeiro/services/fechamento_faturas.py` |
| Importação OFX/planilha | `financeiro/ofx.py`, `financeiro/services/importacao_ofx.py`, `financeiro/services/importacao_planilha.py` |
| Dashboard | `financeiro/services/dashboard.py`, `financeiro/views.py`, `templates/financeiro/dashboard.html` |
| Detalhamento do dashboard | `financeiro/services/detalhamento_dashboard.py`, `templates/financeiro/_dashboard_detalhamento.html` |
| Parcelas | `financeiro/services/cartoes_faturas.py`, `financeiro/services/parcelas_futuras.py` |
| Previsões e baixa | `financeiro/models.py` (`Titulo`, `Liquidacao`), `financeiro/services/titulos.py`, `financeiro/services/fechamento_faturas.py` |
| Classificação | `Categoria`, `RateioCategoria`, `RegraCategoria`, `financeiro/forms.py` |
| PWA | `my_financeiro/pwa.py`, `pwa/service-worker.js`, `templates/pwa/` |

## 3. Modelo de dados

### Entidades e regras relevantes

| Entidade | Finalidade e relações |
|---|---|
| `Conta` | Conta corrente, poupança, carteira ou pagamento; pertence ao usuário; possui saldo inicial/data e limite de crédito. |
| `Cartao` | Cartão de crédito; possui conta de pagamento padrão, limite, identificador externo, dia de fechamento e vencimento. |
| `Categoria` | Classifica receita, despesa ou transferência; pode ter pai, natureza, essencialidade e `computa_resultado`. |
| `Pessoa` | Beneficiário/pagador; nome único por usuário. |
| `EventoFinanceiro` | Fato financeiro lógico: natureza, descrição, data, vencimento, valor, pessoa, âmbito, situação e observação. |
| `RateioCategoria` | Liga evento a uma ou mais categorias com valor próprio. |
| `MovimentoConta` | Movimento efetivo de conta, com valor assinado, data efetiva, documento, histórico e chave de idempotência. |
| `SaldoContaPeriodo` | Cache mensal de entradas, saídas, saldo de fechamento e quantidade de movimentos. |
| `CompraCartao` | Compra original do cartão; liga evento, cartão, estabelecimento, valor total e quantidade de parcelas. |
| `ParcelaCartao` | Item de uma compra em uma fatura/ciclo, com número, total, valor, datas, categoria, pessoa e situação. |
| `Fatura` | Entidade persistida por cartão e ciclo `AAAA-MM`; armazena bruto, créditos, total próprio, transportado, exigido e status. |
| `SerieLancamentoRecorrente` | Vincula ocorrências materializadas de uma recorrência manual; registra usuário, quantidade e intervalo em meses. Cada evento da série possui `numero_recorrencia`. |
| `FechamentoFatura`/`ItemFechamentoFatura` | Snapshot versionado da composição no fechamento. |
| `Titulo` | Obrigação a pagar ou receber; pode apontar para conta, evento e fatura; mantém saldo aberto. |
| `Liquidacao` | Baixa total/parcial de título por movimento de conta, com origem, status e idempotência. |
| `ProgramacaoPagamento` | Reserva de pagamento futuro de um título; admite aplicação parcial. |
| `AplicacaoLiquidacaoProgramacao` | Valor de uma liquidação aplicado a uma programação. |
| `EvidenciaLiquidacao` | Prova de baixa por OFX de conta, OFX de cartão ou manual. |
| `SaldoTransportadoFatura` | Transporte de saldo aberto de uma fatura para outra do mesmo cartão. |
| `Importacao` | Lote OFX ou planilha, hash, adaptador, origem, destino, ciclo, período, saldo e totais. |
| `ItemImportacao` | Registro OFX ou de planilha normalizado, com conteúdo original, chave de conciliação, campos revisados, observação, ação, `revisado_em` e vínculos possíveis. |
| `VinculoTituloImportacao` | Reserva persistida de um título na conciliação manual múltipla de um item OFX de conta; registra o valor reservado e a liquidação efetivada na confirmação. |
| `RegraCategoria` | Regra textual para sugerir categoria, pessoa e âmbito durante importação. |
| `Orcamento` | Limite mensal por categoria e âmbito. Não há indicador de orçamento identificado no dashboard atual. |

### Enums principais

- `Situacao`: `REALIZADO`, `PREVISTO`, `PENDENTE`, `CANCELADO`.
- `NaturezaEvento`: `DESPESA`, `RECEITA`, `ESTORNO`, `PAGAMENTO_FATURA`, `TRANSFERENCIA`.
- `Ambito`: `PESSOAL`, `PROFISSIONAL`, `NAO_DEFINIDO`.
- `Fatura.Status`: `ABERTA`, `FECHADA`, `PAGA`, `PARCIAL`, `EM_CORRECAO`.
- `Titulo.Status`: `ABERTO`, `SUSPENSO`, `LIQUIDADO`.

**IMPLEMENTADO:** fatura, compra, parcela, título, liquidação e fechamento são entidades próprias; não é um modelo baseado apenas em lançamentos.

**IMPLEMENTADO:** a migration `0015_lancamentos_recorrentes` adiciona a série recorrente, os vínculos em `EventoFinanceiro` e a unicidade por série/número. A recorrência é exclusiva de lançamentos manuais; OFX e planilha não criam nem ampliam séries.

## 4. Lançamentos, contas e sinais

`EventoFinanceiro` é o registro lógico. Em conta, um evento realizado normalmente gera `MovimentoConta`; em cartão, gera `CompraCartao` e uma ou mais `ParcelaCartao`.

Em `financeiro/services/lancamentos.py`, `_valor_assinado` usa:

- despesa e pagamento de fatura: valor negativo;
- receita, estorno e transferência: valor positivo.

**IMPLEMENTADO:** o saldo de conta considera `MovimentoConta.valor` e somente eventos com situação `REALIZADO`. A data do saldo é `data_efetiva`, enquanto a listagem também exibe a data lógica do evento.

**PARCIAL:** `TRANSFERENCIA` existe como natureza, mas não foi identificada uma rotina específica que crie e vincule automaticamente os dois lados da transferência.

## 5. Fluxo completo de importação OFX

### Leitura e normalização

1. A view recebe o upload em `views.importar_ofx`.
2. `OFXParser.parse` (`financeiro/ofx.py`) decodifica bytes por encoding declarado, UTF-8, CP1252 ou Latin-1.
3. Tenta `ofxparse`; em falha usa parser tolerante.
4. Detecta conta ou cartão por estruturas `CREDITCARDMSGSRSV1`, `CCSTMTRS`, `CCACCTFROM` e `CCSTMTTRN`.
5. Extrai instituição, banco, identificador da conta, datas do statement, saldo, moeda e transações.
6. Transações carregam identificador/FITID, data, valor, descrição, tipo e documento.
7. `ContaOFXAdapter` e `CartaoOFXAdapter` validam a origem selecionada.
8. `criar_itens` cria `ItemImportacao` e preserva `registro_original`.
9. `natureza_sugerida` define uma natureza inicial; `RegraCategoria` tem precedência para sugerir categoria, pessoa e âmbito.
10. Itens que continuarão como novos lançamentos também podem receber categoria e âmbito sugeridos pelo histórico recente.
11. `_conciliar_item` verifica reimportações confirmadas, pagamentos de fatura e a regra estrita de pré-vínculo.
12. O usuário pode manter, remover ou substituir a sugestão, procurar outro destino ou mudar a ação para criar/ignorar.
13. `confirmar_importacao` revalida os vínculos e executa a criação/vinculação em transação; ao final recalcula faturas e saldos. Uma falha reverte a confirmação e mantém o lote em revisão.

### Campos OFX efetivamente utilizados

`FITID`/identificador, `TRNTYPE`, `DTPOSTED`, `TRNAMT`, `MEMO`, `NAME`, `CHECKNUM`, `REFNUM`, `BANKID`, `ACCTID`, `ORG`/`FI`, `DTSTART`, `DTEND`, `DTASOF`, `BALAMT`, `CURDEF`. O parser de biblioteca também usa payee, routing number, account type, balance e currency quando disponíveis.

### Conta versus cartão

- **Conta:** preserva o sinal do valor e cria `MovimentoConta`; débitos são negativos.
- **Cartão:** usa o ciclo informado no upload, identifica parcela por padrão `N/M` ou `N DE M` na descrição e cria/vincula parcelas. Quando existe `dia_fechamento`, a data da compra é comparada ao ciclo informado apenas para emitir aviso; o ciclo não é alterado automaticamente.
- **Bancos:** não há adaptadores específicos por instituição; há parser genérico e fallback tolerante.

**IMPLEMENTADO:** o ciclo do cartão continua sendo informado pelo usuário. A revisão OFX pode exibir aviso não bloqueante quando a data da transação sugere outro ciclo; `DTSTART`/`DTEND` não movem registros automaticamente.

## 6. Identificação, reimportação e duplicidade

`_chave_item` em `financeiro/services/importacao_ofx.py` produz um hash SHA-256. Origem, destino, ciclo e ocorrência sempre participam da chave. Quando existe FITID/identificador externo, ele é usado como identidade do item; sem identificador, a composição usa data, valor, documento e descrição normalizada. A ocorrência diferencia registros repetidos dentro do mesmo arquivo.

### Reimportação por chave/FITID

**IMPLEMENTADO:** a `chave_conciliacao` é confrontada com itens de lotes `CONFIRMADA` do usuário.

1. Se todos os registros anteriores possuem a mesma data, o mesmo valor e apontam para o mesmo resultado financeiro, o novo item fica `CONCILIADO` e reutiliza evento, movimento, título(s), parcela, evidência e classificação.
2. Se existe exatamente um registro anterior e a data ou o valor mudou, o item fica `DIVERGENTE`.
3. Se existem múltiplos registros anteriores e eles não satisfazem simultaneamente a igualdade de data/valor e de destino, o item fica `PENDENTE` e exige revisão.
4. Um destino novo sugerido por data e valor nunca recebe o tratamento de uma reimportação confirmada: permanece pendente até revisão humana.
5. Movimentos e parcelas consumidos por outra chave confirmada não são reutilizados silenciosamente.

O `hash_arquivo` identifica o conteúdo do lote para auditoria, mas não é único no modelo atual. A migration `0002_importacao_ofx_completa` removeu a constraint `uniq_importacao_usuario_hash` e manteve um índice por usuário/hash. Assim, o mesmo arquivo pode gerar um novo lote de auditoria, enquanto as chaves dos itens impedem a duplicação financeira.

**IMPLEMENTADO no banco:**

- `MovimentoConta(conta, chave_idempotencia)` único quando a chave não está vazia;
- `Liquidacao(titulo, chave_idempotencia)` único quando preenchida;
- `EvidenciaLiquidacao(usuario, tipo, chave)` única;
- `VinculoTituloImportacao(item, titulo)` único, com índices por item/título e título/liquidação para rastreabilidade da conciliação múltipla;
- `SaldoTransportadoFatura(titulo_origem, chave_idempotencia)` único;
- unicidades de fatura/ciclo, parcela/compra/número, série/número da recorrência e item/lote/posição.

### Cenários

| Cenário | Comportamento atual |
|---|---|
| A. Primeiro arquivo | Lote em revisão; confirmação cria ou vincula itens. |
| B. Mesmo arquivo | Novo lote de auditoria; itens já confirmados reutilizam os vínculos sem duplicar registros financeiros. |
| C. Outro arquivo com as mesmas transações | A chave de conciliação identifica as evidências já confirmadas. |
| D. Um destino novo exato | O vínculo é pré-selecionado, mas continua `PENDENTE` e editável. |
| E. Mais de um destino exato | A ação fica em vincular, sem escolha automática do destino. |
| F. Nenhum destino exato | `CRIAR/NOVO` é pré-selecionado; o usuário ainda pode pesquisar manualmente. |
| G. Um crédito/débito para vários títulos | Somente no OFX de conta, a revisão permite marcar títulos e confirma apenas com soma exata; um movimento gera uma liquidação por título. |

## 7. Busca manual, pré-vínculo e classificação

O sistema separa a sugestão automática estrita da busca manual mais ampla.

### Regra estrita de pré-vínculo

Para importação de conta, os destinos automáticos elegíveis são:

- título ativo e aberto, com tipo pagar/receber compatível, conta compatível, vencimento igual à data e saldo aberto igual ao valor absoluto; ou
- movimento da mesma conta e usuário, ainda não consumido, com data efetiva e valor assinado exatos.

Para cartão, a parcela precisa pertencer ao mesmo usuário, cartão e ciclo, estar `PREVISTO`, pertencer a fatura `ABERTA`, ter natureza compatível, ainda não ter sido consumida e possuir data e valor exatos. Quando o OFX informa `N/M`, número e total também devem coincidir. Na planilha, o número técnico inicial `1` não é tratado como marcador efetivo de parcela.

Resultados:

- um destino exato: `VINCULAR/PENDENTE`, com destino pré-selecionado;
- mais de um destino exato: `VINCULAR/PENDENTE`, sem escolha automática;
- nenhum destino exato: `CRIAR/NOVO` pré-selecionado.

A pré-seleção permanece editável. Somente uma reimportação anteriormente confirmada pode ser marcada automaticamente como conciliada. Na confirmação, o destino é revalidado; parcela realizada, fatura fechada ou destino consumido fazem a confirmação falhar sem criar duplicidade.

### Busca manual

`Buscar semelhantes` usa pontuação por valor, data, categoria, descrição e pessoa. Para cartão, esse escopo primeiro exige a mesma data e diferença de valor de no máximo um centavo; a pontuação ordena os candidatos restantes. `Buscar em todos` remove esse corte de semelhança, mas preserva as restrições estruturais.

Para parcelas, mesmo a busca ampla continua limitada a usuário, cartão, ciclo, situação `PREVISTO`, fatura `ABERTA`, natureza compatível e destino ainda disponível. Para conta, títulos continuam limitados a ativos/abertos, tipo compatível, saldo suficiente e conta selecionada ou ainda não definida; movimentos continuam limitados à mesma conta e usuário, sinal compatível e destino ainda não consumido.

### Conciliação manual de vários títulos por item OFX de conta

**IMPLEMENTADO:** exclusivamente na importação OFX de conta corrente, um item pode ser associado manualmente a dois ou mais títulos `ABERTO` compatíveis. Esse recurso não se aplica a movimento já realizado, parcela de cartão, OFX de cartão nem planilha.

Regras obrigatórias:

- os títulos pertencem ao mesmo usuário, têm tipo compatível com o sinal do item e pertencem à conta importada ou não possuem conta definida;
- cada título está ativo, `ABERTO` e com saldo positivo;
- a soma dos saldos abertos selecionados é exatamente igual ao valor absoluto do item OFX; não há baixa parcial, arredondamento ou saldo remanescente nesse fluxo;
- a seleção é sempre manual. A sugestão automática continua limitada a uma única correspondência exata por data e valor;
- a revisão exibe quantidade, total selecionado, valor do OFX e diferença, e não permite salvar enquanto a diferença não for zero.

Na confirmação, o lote, o item, a conta e todos os títulos são bloqueados e revalidados. O sistema cria ou reutiliza um único `MovimentoConta` idempotente do OFX e cria uma `Liquidacao` por título, com evidência individual. O título passa a `LIQUIDADO` quando sua totalidade é baixada; o `EventoFinanceiro` previsto de origem permanece `PREVISTO` como referência de planejamento.

Na reimportação pelo mesmo FITID/chave, os títulos e liquidações já conciliados são exibidos novamente sem criar novo movimento ou nova baixa. Ao desfazer o lote que criou a conciliação, as liquidações do grupo são removidas, os títulos são recalculados e o movimento importado é removido quando não estiver usado por outra importação confirmada.

### Classificação pelo histórico recente

A sugestão histórica é aplicada somente a itens `NOVO/CRIAR`. Para conta, examina movimentos realizados do mês-calendário anterior; para cartão, parcelas realizadas do ciclo anterior do mesmo cartão. Pagamentos de fatura, transferências e estornos são excluídos dessa inferência.

O sistema pode sugerir categoria quando ela está vazia e âmbito quando ele não foi informado explicitamente. Uma `RegraCategoria` ativa e os valores fornecidos na planilha têm precedência. Descrição e valor exatos podem gerar sugestão quando a classificação histórica é inequívoca; nos demais casos é necessário um vencedor repetido, sem empate. Histórico dividido ou ambíguo não preenche o item. Essa regra reutiliza o schema existente e não exige migration.

### Proteção de itens revisados

`ItemImportacao.revisado_em` protege o trabalho manual. A aplicação em massa valida lote e IDs, altera somente itens ainda não revisados, informa quantos foram preservados e falha sem gravações quando o escopo contém apenas itens revisados. A ação genérica `VINCULAR` não é aplicada em massa porque cada vínculo exige destino próprio. A edição individual de item revisado permanece disponível.

**IMPLEMENTADO:** baixa de título pode ser parcial; o saldo aberto não pode ser ultrapassado. A liquidação usa `Liquidacao`, não cria uma nova despesa para cada baixa.

## 8. Status e ciclo de vida

### Eventos e parcelas

- `REALIZADO`: entra no saldo de conta quando há movimento; entra na análise do dashboard quando natureza/categoria permitem.
- `PREVISTO`: gera `Titulo` quando aplicável; não cria movimento efetivo. Parcela prevista não entra na fatura confirmada, mas entra na composição projetada da fatura.
- `PENDENTE`: existe como enum e bloqueia fechamento quando usado em parcela; não foi identificado fluxo completo de transição para evento de conta.
- `CANCELADO`: não compõe os totais confirmado ou projetado da fatura; permanece disponível para rastreabilidade da operação.

### Fatura e título

Fatura começa `ABERTA`, vai a `FECHADA` no fechamento, `PARCIAL` após baixa/transportes com saldo restante, `PAGA` quando o título é liquidado, e `EM_CORRECAO` quando reaberta com liquidações/transportes preservados. Título começa `ABERTO`, fica `LIQUIDADO` quando totalmente baixado, ou `SUSPENSO` em reabertura sem vínculos preservados.

## 9. Cartões, ciclos, parcelas e faturas

### Ciclo

O sistema usa a string `AAAA-MM` como ciclo. `proximo_ciclo` soma meses por índice calendário e continua sendo usado para as parcelas seguintes. O ciclo inicial continua sendo informado pelo usuário.

**IMPLEMENTADO:** `Fatura.ciclo` representa o mês esperado de vencimento/pagamento. `aviso_ciclo_cartao` usa primeiro o vencimento, quando informado; nesse caso, o mês do vencimento é o ciclo esperado. Sem vencimento, usa a data da compra e `Cartao.dia_fechamento`: compra até o fechamento, inclusive, sugere o mês seguinte; compra posterior sugere dois meses à frente. Sem vencimento e sem dia de fechamento, não há aviso por falta de referência segura. Em item parcelado de OFX ou planilha, a estimativa derivada da compra é deslocada em `N - 1` meses para a parcela `N/M`; vencimento próprio de parcela não recebe novo deslocamento. A divergência apenas informa o usuário, preserva o ciclo informado e não bloqueia gravação ou confirmação.

Exemplos com fechamento no dia 25: compra em 01/09/2026 sugere ciclo `10/2026`; compra em 19/06/2026 na parcela 4/5 sugere `10/2026`; compra em 08/10/2026 sugere `11/2026`; compra em 27/10/2026 sugere `12/2026`; compra em 08/10/2026 com vencimento em 11/11/2026 sugere `11/2026`.

Virada de ano é tratada pela soma de meses. Não há tratamento especial para fim de semana, feriado, fechamento em dia inexistente ou ajuste bancário, pois essas regras não fazem parte do escopo implementado.

### Parcelamento

`criar_compra_cartao` cria um `EventoFinanceiro`, uma `CompraCartao` pai e N `ParcelaCartao`, uma em cada ciclo. O valor é distribuído em centavos: quociente mais um centavo nas primeiras parcelas quando há resto. A primeira parcela recebe a situação informada; as demais começam `PREVISTO`.

Os vencimentos são calculados por `_somar_meses`, preservando o dia limitado ao último dia do mês. A edição altera somente a parcela selecionada; não há rotina identificada para editar todas as parcelas em lote. Exclusão pela view é da parcela/evento conforme o fluxo da view; não foi identificada uma regra documentada de exclusão em cascata de toda a compra.

**IMPLEMENTADO:** OFX de cartão reconhece parcela efetiva e pode conciliá-la com parcela prevista. Divergência de valor é rejeitada na validação automática, ficando para revisão.

### Fatura

`recalcular_fatura` mantém a composição operacional persistida: soma parcelas `REALIZADO`, despesas entram em `total_bruto`, estornos/receitas em `total_creditos`, e `total = bruto - créditos`. Transporte confirmado/incorporado é somado em `total_transportado`; `total_exigido = total + transportado`.

Na apresentação, `financeiro/services/cartoes_faturas.py::calcular_totais_parcelas` é a composição compartilhada pelo dashboard e pela tela de cartões:

- `total_confirmado`: somente parcelas `REALIZADO`;
- `total_projetado`: parcelas `REALIZADO`, `PREVISTO` e `PENDENTE`;
- ambos excluem `CANCELADO` e `PAGAMENTO_FATURA`;
- `ESTORNO` e `RECEITA` reduzem os dois totais;
- saldo transportado permanece separado e não é incorporado ao total projetado; compõe o saldo exigível operacional da fatura.

Fechamento exige que não existam parcelas `PREVISTO`/`PENDENTE`, cria snapshot e um único `Titulo` a pagar vinculado à fatura. Pagamento parcial é suportado por `Liquidacao`, `saldo_aberto` e status `PARCIAL`. Saldo aberto pode ser transportado para outra fatura do mesmo cartão, mediante ação explícita ou identificação de “saldo anterior” no OFX.

**IMPLEMENTADO:** não foi identificada duplicação de despesa no fechamento; o pagamento é obrigação/liquidação e saída de conta. A alteração de apresentação não altera `Fatura.total`, `Fatura.total_exigido`, `Titulo.saldo_aberto` ou o fluxo de pagamento.

## 10. Pagamento de fatura: resultado versus caixa

O fluxo é:

`compra cartão → parcela/fatura → fechamento → título a pagar → movimento negativo na conta → liquidação`.

O pagamento manual cria evento `PAGAMENTO_FATURA` e movimento negativo. O dashboard exclui `PAGAMENTO_FATURA` e `TRANSFERENCIA` da análise de resultado em `_adicionar_linha_analitica`, mas o movimento continua no fluxo e no saldo da conta.

**IMPLEMENTADO:** essa é a regra equivalente a `computaResultado = false` para pagamento de fatura, embora a categoria possa existir com esse campo falso. A exclusão do dashboard é pela natureza, portanto protege o caso mesmo se a categoria estiver ausente.

**DIVERGÊNCIA/PONTO DE ATENÇÃO:** outras telas/consultas que não usam `_adicionar_linha_analitica` devem ser auditadas antes de afirmar que toda a aplicação exclui pagamentos do resultado. A listagem de lançamentos exclui parcelas de pagamento de fatura, mas mostra movimentos de conta.

## 11. Categorias e `computa_resultado`

Categoria possui tipo (`DESPESA`, `RECEITA`, `TRANSFERENCIA`), natureza (`PESSOAL`, `EMPRESARIAL`, `AMBOS`), essencialidade e `computa_resultado`.

No dashboard, se uma categoria existe e `computa_resultado=False`, o rateio é descartado da análise. Sem categoria, o valor entra na análise quando o filtro de natureza é `all`, como “A classificar”. Categorias filhas são agrupadas pela categoria superior para gastos por categoria; essencialidade e natureza usam a categoria do rateio.

**IMPLEMENTADO:** `computa_resultado` controla receitas, despesas, créditos e resultado analítico. Categorias não computáveis não são somadas nesses indicadores.

**IMPLEMENTADO:** movimentos realizados continuam afetando integralmente saldo atual e fluxo de caixa, independentemente da categoria. Títulos futuros usam a proporção computável dos rateios; títulos 100% não computáveis ficam fora do saldo/fluxo projetado. Faturas e limites de cartão permanecem independentes da categoria.

## 12. Fluxo de caixa x resultado financeiro

| Conceito | Base atual |
|---|---|
| Resultado | Movimentos realizados de conta + parcelas cujo vencimento está no intervalo selecionado, excluindo pagamento de fatura/transferência e categorias sem `computa_resultado`; fórmula apresentada como `receitas - despesas líquidas`. |
| Fluxo de caixa | Movimentos realizados de conta por sinal; entradas positivas e saídas negativas, incluindo pagamento de fatura e demais movimentos. |
| Saldo atual | Saldo inicial + movimentos realizados até o fim do período. Usa `SaldoContaPeriodo` quando disponível. |
| Projeção | Saldo atual + títulos a receber previstos - títulos a pagar previstos, incluindo programação residual. |
| Obrigação do cartão | Fatura/título/parcelas e transportes; não é saída de conta até a liquidação. |

## 13. Composição dos indicadores do Dashboard

A Visão Geral é produzida por `financeiro/services/dashboard.py::consultar_dashboard`, chamado por `financeiro/views.py::dashboard`. O intervalo principal é inclusivo e usa `date_from` e `date_to`, aceitando `DD/MM/AAAA` e ISO. Sem intervalo válido, usa o mês corrente; `period=AAAA-MM` permanece por compatibilidade. Intervalos parciais são comparados ao período imediatamente anterior de igual duração, enquanto meses completos usam o mês anterior. A evolução termina no mês da data final selecionada.

| Indicador | Fonte e fórmula | Previsto | Filtros |
|---|---|---|---|
| Receitas | `_analisar_dados`; eventos/parcelas `RECEITA`, valor absoluto. | Não | intervalo, conta/cartão/origem/natureza e categoria computável. |
| Despesas | Despesas brutas menos estornos elegíveis de despesas; `resumo.despesas` representa o valor líquido. | Não | mesmos filtros. |
| Créditos analíticos | Acumulador interno de estornos com categoria do tipo `DESPESA` e `computa_resultado=True`; estorno sem categoria elegível não reduz a análise. | Não | mesmos filtros. |
| Resultado | `receitas - despesas líquidas`. | Não | mesmos filtros. |
| Entradas/Saídas | `_fluxo_movimentos` sobre `MovimentoConta` realizado; sinal do movimento. | Não | período e conta; selecionar somente um cartão não restringe as contas nem o caixa. |
| Saldo atual | `_saldo_contas`/`saldo_conta_ate`; saldo inicial + movimentos até `fim`. | Não | contas selecionadas. |
| Saldo projetado | saldo atual + recebimentos previstos - saídas previstas. | Sim | contas e período de previsão. |
| Fatura confirmada | `calcular_totais_parcelas` sobre parcelas cujo vencimento está no intervalo selecionado; somente `REALIZADO`, com cancelados e pagamentos de fatura excluídos e créditos reduzindo o valor. | Não | cartão e intervalo de vencimento. |
| Fatura projetada | `calcular_totais_parcelas` sobre parcelas do mesmo recorte com situação `REALIZADO`, `PREVISTO` ou `PENDENTE`, com a mesma exclusão de cancelados/pagamentos e abatimento de créditos. `faturaAtual` permanece compatível e representa este valor. | Sim | cartão e intervalo de vencimento. |
| Gastos por categoria | categorias superiores; percentuais sobre despesas líquidas positivas. | Não | `computa_resultado`, intervalo, origem, natureza. |
| Composição por essencialidade | soma por `ESSENCIAL`, `NECESSARIO_VARIAVEL`, `PROFISSIONAL`, `ESTILO_VIDA`, `SUPERFLUO`, `FINANCEIRO`. | Não | mesmos filtros. |
| Distribuição por natureza | soma `PESSOAL`, `EMPRESARIAL`, `AMBOS`. | Não | mesmos filtros. |
| Gastos controláveis | soma `ESTILO_VIDA + SUPERFLUO`; percentual sobre despesas líquidas. | Não | mesmos filtros. |
| Simulador | primeiros 10 gastos positivos por categoria; 20% mensal e 2,40 vezes anual. | Não | depende das categorias atuais. |
| Compromissos | títulos ativos com saldo aberto nos próximos 7/30 dias. | Sim | contas e datas correntes. |
| Pontos de atenção | aumento de categoria ≥20%, controláveis ≥30% das despesas e termos juros/tarifa/taxa/encargo. | Não | compara período anterior. |
| Evolução | seis ciclos terminando no selecionado; receita, despesa e resultado. | Não | mesmos filtros. |
| Limite de cartão | Faturas abertas usam parcelas válidas, créditos/estornos, transportes do destino e estimativas futuras; fechadas, parciais ou em correção usam saldo aberto de título ativo, positivo e não liquidado. Faturas pagas e títulos liquidados/inativos não comprometem limite. | Sim | cartões filtrados; mês corrente como ciclo base, independentemente do intervalo principal. |

### Observações do dashboard

- Dashboard e tela de cartões usam a mesma fórmula em `calcular_totais_parcelas`. Os valores coincidem quando recebem o mesmo conjunto temporal de parcelas; o dashboard recorta por vencimento no intervalo, enquanto a tela de cartões consulta a igualdade de `Fatura.ciclo`.
- `resumo.faturaAtual` e `metricas.fatura` continuam disponíveis para compatibilidade e representam explicitamente o total projetado.
- O dashboard também expõe `faturaConfirmada`/`faturaProjetada` e `compromissos.fatura_confirmada`/`fatura_projetada` para apresentação separada.
- O filtro de conta restringe cartões pela `conta_pagamento_padrao`; isso não significa que a compra ocorreu na conta. A relação não é invertida: selecionar somente um cartão não filtra as contas usadas no saldo ou no fluxo de caixa.
- A composição analítica ignora pagamentos/transferências por natureza e ignora categorias não computáveis, mas o fluxo de caixa não aplica essa exclusão.
- `NEUTRO` não está em `ESSENCIALIDADES_COMPOSICAO`; portanto não aparece como bloco da composição, embora categorias neutras possam existir.
- A mesma despesa líquida alimenta KPIs, categorias, essencialidade, natureza, gastos controláveis, percentuais, comparação, evolução e detalhamento. Fluxo de caixa, saldo, fatura e limite preservam suas bases próprias.
- No limite, estimativas já materializadas são eliminadas pela chave `(compra_id, numero)`. O percentual financeiro pode exceder 100%, mas a largura visual da barra é limitada a 100%.
- O painel de posição por conta calcula seu saldo atual até a data de hoje, mesmo quando o intervalo principal é histórico. Suas previsões usam o fim do intervalo selecionado como horizonte; o limite de cartão permanece ancorado no mês corrente.

### Detalhamento dos indicadores

Indicadores não vazios de essencialidade, categoria superior, natureza e gastos controláveis abrem um modal consultivo. O detalhamento reutiliza contribuições e filtros do dashboard, consolida rateios e estornos, exibe total e quantidade, preserva observações com quebras de linha e oferece ligação para a listagem completa de lançamentos. Não há ação de edição ou exclusão no modal.

O endpoint exige autenticação e isolamento por usuário. Indicador inválido ou categoria pertencente a outro usuário é rejeitado.

### Ocultação visual de valores

A Visão Geral possui controle para ocultar valores monetários e percentuais da página inteira. A preferência é armazenada somente no navegador, em `localStorage`, com a chave `my-financeiro.dashboard.values-hidden`; não há persistência em banco nem sincronização entre dispositivos.

O mascaramento é reaplicado ao modal carregado dinamicamente e aos cálculos do simulador. Textos, percentuais, tooltips e atributos ARIA numéricos são ocultados, enquanto cores, barras e proporções permanecem visíveis. Trata-se de privacidade visual, não de controle de acesso ou criptografia. Se o armazenamento local estiver indisponível, o dashboard continua funcionando, mas a preferência pode não persistir.

## 14. Previsões, realizados e recorrência manual

Conta prevista: `criar_lancamento` cria evento `PREVISTO` e `Titulo`, sem `MovimentoConta`. O dashboard usa o título em projeções; não entra em receita/despesa realizados nem no saldo atual.

Quando um OFX é vinculado ao título, `_confirmar_vinculo_titulo` cria o evento realizado/movimento e chama `liquidar_titulo`; pode copiar rateios proporcionalmente. O título mantém saldo aberto em baixa parcial.

Parcela prevista é realizada no vínculo de OFX de cartão, atualizando situação e valor. A fatura é recalculada.

### Recorrência implementada

A recorrência disponível é manual e materializada no momento da criação. Não é um agendador que cria registros posteriormente em segundo plano.

O usuário informa quantidade de ocorrências e intervalo em meses inteiros. O sistema cria eventos independentes ligados pela mesma `SerieLancamentoRecorrente`:

- a primeira ocorrência mantém a situação escolhida;
- as ocorrências seguintes são criadas como `PREVISTO`;
- cada ocorrência mantém o valor integral;
- datas, vencimentos e ciclos avançam pelo intervalo informado;
- recorrência de conta com mais de uma ocorrência exige vencimento;
- no cartão, cada ocorrência é uma compra independente, não uma parcela de uma única compra.

Ao editar uma ocorrência, o usuário pode alterar somente ela ou replicar os campos permitidos para as futuras ainda previstas. A opção “Manter agenda original” preserva data, vencimento, ciclo e situação de cada ocorrência.

A exclusão opcional de futuros atinge somente ocorrências posteriores `PREVISTO` e editáveis. São preservados lançamentos realizados, importados, títulos liquidados/programados e compras em faturas bloqueadas. OFX e planilha permanecem fora da recorrência.

**NÃO IDENTIFICADO:** scheduler, Celery, cron ou outro processamento que gere novas ocorrências no futuro; todas são materializadas na criação manual.

### Observações de lançamentos e importações

A observação informada pelo usuário percorre os fluxos de conta, cartão, OFX e planilha. Na listagem de lançamentos e no detalhamento do dashboard ela é exibida integralmente em linha adicional, preservando quebras de linha e omitindo o bloco quando vazia.

Os importadores não acrescentam mais textos técnicos como `Importado do lote #N.` ou `Compra futura importada de planilha.`. Uma chave `observacao` explicitamente vazia permanece vazia; somente a ausência da chave pode acionar um fallback legado.

A migration de dados `0014_remover_observacoes_automaticas_importacao` remove somente o marcador automático e seu sufixo, preserva o texto revisado anterior ao marcador e esvazia observações que continham apenas o texto técnico. A remoção histórica não possui reversão automática.

### Clonagem e pessoa em texto livre

A ação de clonar abre um novo formulário preenchido a partir do lançamento de origem, mas não grava nada antes da confirmação. Data e vencimento são limpos para nova escolha; em cartão, a referência copiada corresponde a uma compra de uma parcela, sem duplicar silenciosamente todo o parcelamento original. O novo lançamento é independente do anterior.

O formulário aceita selecionar uma `Pessoa` do próprio usuário ou manter apenas `pessoa_nome_livre`. Texto livre é salvo no lançamento e nas parcelas aplicáveis, sem criar silenciosamente um cadastro de pessoa. Se o texto continuar igual à pessoa selecionada na lista, o vínculo cadastrado é preservado e o campo livre é limpo; se o usuário alterar o texto, prevalece o nome livre.

## 15. Estornos, créditos e valores negativos

No cartão, estorno é natureza `ESTORNO` e reduz a fatura por `total_creditos`; receita também é tratada como crédito em várias somas. OFX positivo é associado a estorno no vínculo de parcela, enquanto débito negativo é associado a despesa. O parser preserva o sinal original.

**NÃO IDENTIFICADO:** regra específica de vínculo automático de estorno a uma compra original; o código trata o crédito no total e na natureza, mas não localiza uma associação obrigatória por compra.

## 16. Datas, filtros e agrupamento

- `EventoFinanceiro.data`: data lógica/competência exibida.
- `MovimentoConta.data_efetiva`: data usada para caixa, saldo e filtro de movimentos realizados.
- `EventoFinanceiro.vencimento`/`Titulo.vencimento`: previsão/obrigação.
- `CompraCartao.data_compra`/`ParcelaCartao.data_original`: data de compra exibida.
- `ParcelaCartao.vencimento`: vencimento da parcela; não define sozinho o ciclo.
- `Fatura.ciclo`: chave do ciclo e filtro de fatura/dashboard de cartão.
- `Importacao.data_*`: metadados do arquivo.

No dashboard, a análise de conta usa `EventoFinanceiro.data` como competência, enquanto saldo e caixa usam `MovimentoConta.data_efetiva`, inclusive quando a data final está no meio do mês. A interface atual expõe intervalo, conta e cartão. O backend também aceita origem e natureza, mas os controles correspondentes estão comentados no template e não devem ser descritos como filtros visíveis.

### Filtros da página de lançamentos

Na primeira abertura, quando `date_from` e `date_to` não foram enviados, o sistema preenche o primeiro e o último dia do mês atual. Datas submetidas pelo usuário, inclusive valores explicitamente vazios, não são substituídas pelo padrão.

- período mensal em conta: filtra por `EventoFinanceiro.data`;
- intervalo explícito em conta: filtra pela data do evento;
- período mensal em cartão: exige igualdade com `Fatura.ciclo`;
- intervalo explícito em cartão: filtra pelo vencimento da parcela;
- a tabela exibe separadamente a data original da compra e o vencimento da fatura/parcela.

Os filtros podem combinar conta, cartão, origem, categoria, categoria superior, natureza do lançamento, natureza/essencialidade da categoria, `computa_resultado`, pessoa, situação e busca textual. “Categoria superior” lista somente categorias sem pai; “Categoria” lista categorias com pai usando `Filha (Pai)`. Selecionar uma superior inclui seus descendentes. A propriedade/isolamento por usuário é aplicada nas consultas principais.

### Agrupamento visual por fatura

A opção de agrupar lançamentos de cartão por fatura é exclusivamente visual e executada depois dos filtros:

- linhas de conta permanecem individuais;
- linhas de cartão são agrupadas por `fatura_id`;
- faturas e ciclos diferentes não são misturados;
- a linha consolidada mostra cartão, ciclo, vencimento, status, quantidade e total filtrado;
- ações individuais de editar, clonar ou excluir não são apresentadas;
- desligar a opção restaura as linhas analíticas.

Os totalizadores são calculados antes da consolidação; portanto, o agrupamento não altera valores financeiros. O vencimento persistido da fatura é usado sempre que estiver preenchido, independentemente do status; na ausência dele, o sistema calcula a data pelo ciclo e pelo dia de vencimento do cartão.

## 17. Regras no frontend

Forms e templates aplicam validações de entrada: cartão exige cartão; pagamento de fatura exige conta, cartão, ciclo e situação realizado; parcelamento só aceita despesa e limita quantidade; filtros e opções de ciclo são apresentados no template. Templates exibem totais, sinal, marcadores de parcela e ações conforme o contexto.

**IMPLEMENTADO:** os totais de composição de fatura usados no dashboard e na tela de cartões foram centralizados no backend em `calcular_totais_parcelas`; os templates apenas exibem os valores e rótulos recebidos.

**IMPLEMENTADO:** divergências de data/ciclo são exibidas como aviso no formulário de compra manual e na revisão OFX. O aviso não é erro de validação, não muda o status do item e não impede confirmação/gravação.

**IMPLEMENTADO:** o layout registra a PWA, oferece instalação quando o navegador disponibiliza `beforeinstallprompt` e mantém o mesmo loading de navegação/formulários nas telas autenticadas e no login. A presença do botão não garante que a instalação esteja disponível: isso depende do navegador e de contexto seguro.

## 18. Regras no backend

As regras principais estão em:

- `financeiro/services/importacao_ofx.py`: fingerprint, classificação, candidatos, pré-vínculo, confirmação, desfazimento, criação de eventos/parcelas e recálculo de fatura.
- `financeiro/services/importacao_planilha.py`: leitura XLSX/CSV, planejamento de compras, duplicidade e reaproveitamento do pipeline de revisão.
- `financeiro/services/fechamento_faturas.py`: fechamento, título, programação, baixa, pagamento manual, transporte e reabertura.
- `financeiro/services/cartoes_faturas.py`: compra parcelada, distribuição de centavos, ciclo informado e edição de parcela.
- `financeiro/services/dashboard.py`: resultado líquido, caixa, projeções, categorias, essenciais, economia, alertas, limites e leitura do total projetado compartilhado.
- `financeiro/services/detalhamento_dashboard.py`: composição consultiva dos indicadores e ligação com lançamentos filtrados.
- `financeiro/services/cartoes_faturas.py::calcular_totais_parcelas`: composição confirmada/projetada de fatura.
- `financeiro/services/cartoes_faturas.py::aviso_ciclo_cartao`: validação informativa da data contra o fechamento.
- `financeiro/services/saldo_contas.py`: reprocessamento mensal e saldo por data.
- `financeiro/services/lancamentos.py`: criação, recorrência, edição, exclusão segura, filtros, agrupamento e assinatura de valores.
- `my_financeiro/pwa.py` e `pwa/service-worker.js`: manifesto, ícones, service worker e fallback offline.
- `financeiro/models.py`: enums, relações e constraints.

## 19. Regras no banco

Há foreign keys com `PROTECT`, `CASCADE` ou `SET` conforme entidade; constraints únicas para fatura/ciclo, parcela, rateio, título por fatura, série/número recorrente, idempotência e evidência. Não foram identificados triggers ou procedures de banco. A maior parte da regra de negócio está no Python.

As migrations `0001` a `0015` aparecem aplicadas no ambiente consultado. `0014` corrige observações históricas e `0015` cria a estrutura da recorrência. Em 16/10/2026, `makemigrations --check --dry-run` propunha a próxima migration para renomear o índice de `SaldoContaPeriodo`; essa renomeação não foi criada durante a revisão documental. A evolução de 19/10 ocupou a numeração `0016` com `vinculo_titulo_importacao`; por isso, a renomeação permanece como possível `0017` independente.

## 20. Matriz de impacto atual

| Evento | Saldo conta | Receita | Despesa | Fatura | Fluxo caixa | Resultado |
|---|---:|---:|---:|---:|---:|---:|
| Receita recebida | Sim | Sim | Não | Não | Entrada | Sim |
| Despesa em conta | Sim | Não | Sim | Não | Saída | Sim se categoria computável |
| Compra cartão | Não | Não | Sim no intervalo de vencimento | Sim | Não imediato | Sim no intervalo se parcela realizada e categoria computável |
| Parcela prevista | Não | Não | Não realizado | Somente na projeção | Não | Não |
| Pagamento de fatura | Sim | Não | Não no dashboard | Reduz título | Saída | Não |
| Transferência própria | Depende do movimento | Não | Não no dashboard | Não | Sim | Não no dashboard |
| Saque | Sim | Não | Depende da categoria/natureza | Não | Saída | Depende; não há rotina patrimonial específica identificada |
| Estorno cartão | Não | Não | Reduz a despesa líquida quando elegível | Reduz por crédito | Não imediato | Melhora o resultado quando ligado a categoria de despesa computável |
| Lançamento previsto | Não | Não realizado | Não realizado | Se título de fatura, depende | Não | Não |
| Empréstimo | Depende do evento lançado | Depende | Depende | Não identificada | Depende | Depende da natureza/categoria |
| Tarifa bancária | Sim se movimento | Não | Sim se classificada | Não | Saída | Sim se `computa_resultado=True` |

## 21. Matriz `computa_resultado`

| Operação | Tipo | Recomendado | Impacta saldo | Impacta resultado atual |
|---|---|---:|---:|---:|
| Receita normal | RECEITA | Sim | Sim quando realizada | Sim |
| Despesa normal | DESPESA | Sim | Sim em conta / não no momento da compra cartão | Sim |
| Compra cartão | DESPESA | Sim | Não imediato | Sim quando parcela realizada e categoria computável |
| Pagamento fatura | PAGAMENTO_FATURA | Não | Sim | Não |
| Transferência própria | TRANSFERENCIA | Não | Sim nos lados | Não |
| Saque | DESPESA/TRANSFERENCIA conforme cadastro | Não | Sim | Depende da implementação/categoria |
| Juros | DESPESA | Sim | Sim | Sim |
| Tarifa | DESPESA | Depende | Sim | Depende da categoria |
| Ajuste de saldo | Não identificado como operação própria | Não | Depende | Não deveria duplicar resultado |

As colunas “Recomendado” são orientação de domínio, não afirmação de que exista uma configuração automática para cada operação.

## 22. Testes e cobertura atual

Foram localizados testes em `financeiro/tests/` para OFX/parser, importação, reimportação, conciliação, cartão/fatura, fechamento/pagamentos, parcelas futuras, dashboard, categorias, lançamentos, pessoas, menu e formatação.

Há cenários explícitos para reimportação sem duplicidade, histórico de classificação, pré-vínculo estrito, busca ampla, proteção de revisados, parcelas previstas, pagamento de fatura, baixa parcial, recorrência, agrupamento, privacidade do dashboard, PWA e segurança por usuário.

### Verificação executada em 19/10/2026

- `manage.py check`: aprovado, sem problemas.
- `manage.py test financeiro.tests --keepdb`: 258 testes aprovados.
- a expectativa textual do modal de lançamentos foi reconciliada com a orientação atual sobre lançamento único, compra parcelada e recorrência.
- `showmigrations financeiro`: migrations `0001` a `0015` aplicadas.
- `git diff --check`: sem erro de whitespace nos arquivos rastreados; apenas avisos LF/CRLF.

Na atualização de 19/10, foi criada a migration `0016_vinculo_titulo_importacao` para a conciliação múltipla de títulos por OFX de conta. `makemigrations --check --dry-run` ainda propõe somente a renomeação preexistente do índice de `SaldoContaPeriodo`, agora como possível `0017`; ela não foi incluída nesta evolução.

Essas execuções não constituem validação de instalação PWA, service worker real, `localStorage`, interação do modal/simulador, navegador móvel, Docker, proxy HTTPS, PostgreSQL de produção ou ambiente publicado.

## 23. Inconsistências e riscos identificados

### ALTO — Mesmo conceito de fatura usava fórmulas diferentes — CORRIGIDO

O dashboard e a tela de faturas agora usam `calcular_totais_parcelas`. O usuário distingue fatura confirmada e projetada; previsões não são apresentadas como confirmadas. `faturaAtual` continua compatível, mas representa explicitamente o total projetado.

### ALTO — Dias de fechamento/vencimento não participavam do ciclo — TRATADO SEM REALOCAÇÃO

`Fatura.ciclo` representa o mês esperado de vencimento/pagamento. Vencimento explícito define o ciclo esperado. Sem ele, compra até o fechamento, inclusive, sugere pagamento no mês seguinte; compra posterior sugere dois meses à frente. Em `N/M`, a estimativa derivada da compra avança `N - 1` meses. O aviso não altera o ciclo informado nem move compras.

### RESOLVIDO — Reimportação do mesmo arquivo

A migration `0002_importacao_ofx_completa` removeu a unicidade por usuário/hash. O mesmo arquivo pode criar outro lote, e a `chave_conciliacao` reutiliza vínculos confirmados sem duplicar eventos ou movimentos. Os testes atuais de importação cobrem reenvios sucessivos.

### MÉDIO — `computa_resultado` não é regra universal

Dashboard aplica a flag, mas saldo, fatura, limites e algumas consultas seguem natureza/situação próprias. Impacto: usuário pode interpretar “não computa” como exclusão de todo indicador.

### MÉDIO — Transferência e saque sem fluxo patrimonial completo identificado

Há enums/categorias, mas não foi encontrada rotina que crie automaticamente dois lados de transferência ou uma carteira vinculada para saque. Impacto: risco de caixa/resultados manuais inconsistentes.

### BAIXO — Ausência de adaptadores por banco

Parser genérico e fallback suportam estruturas OFX, mas não há regra específica por banco. Impacto: variações de descrição, parcelamento ou sinais podem exigir revisão manual.

### MÉDIO — Estado de migrations não está limpo

O banco consultado possuía `0001` a `0015` aplicadas na verificação de 16/10. A migration `0016_vinculo_titulo_importacao` deve ser aplicada antes de usar a conciliação múltipla; separadamente, `makemigrations --check --dry-run` ainda propõe renomear o índice de `SaldoContaPeriodo` como possível `0017`.

### BAIXO — Teste textual de lançamentos desatualizado — CORRIGIDO

A expectativa foi atualizada para a orientação atual do formulário sobre lançamento único, compra parcelada e recorrência. O teste focado e a suíte completa com 258 casos foram aprovados em 19/10/2026.

## 24. Funcionalidades ainda não identificadas ou fora do escopo

- Ajuste automático de vencimento para fins de semana/feriados.
- Agendador que crie novas ocorrências recorrentes em segundo plano; a recorrência manual materializada já está implementada.
- Rotina automática de transferência patrimonial entre contas.
- Associação conclusiva de estorno à compra original.
- Indicador de orçamento usando `Orcamento`.
- Conciliação automática de um destino novo sem revisão humana.

Recorrência manual, pagamento parcial, transporte de saldo, fechamento versionado, baixa parcial e importação de compras futuras estão implementados e não devem continuar descritos como evoluções futuras.

## 25. Dívida técnica relacionada às regras financeiras

- A composição de apresentação da fatura foi centralizada, mas o cálculo operacional persistido/fechamento continua em `fechamento_faturas.py` e `recalcular_fatura`; são conceitos distintos e devem permanecer documentados.
- O ciclo continua sendo calculado por soma de meses; o dia de fechamento gera aviso, não realocação.
- Resultado é centralizado no dashboard, mas outras telas possuem somas próprias.
- A camada de persistência está espalhada em services/views, sem repository explícito.
- `SaldoContaPeriodo` é cache materializado que exige reprocessamento após alteração/exclusão de movimentos.
- O comportamento de mesmo arquivo OFX depende de hash para rastreabilidade, chave por item e vínculos de evidência; o hash não é mais uma restrição única.
- O nome do índice de `SaldoContaPeriodo` ainda produz uma migration de renomeação pendente.
- A suíte de lançamentos possui uma expectativa textual desatualizada.
- A PWA depende de HTTPS/localhost; o Compose não fornece terminação TLS por si só.
- As suítes foram executadas no `.venv`; ainda não houve validação em produção, PostgreSQL real, Docker publicado ou navegador visual.

## 26. Rastreabilidade resumida

| Regra | Evidência |
|---|---|
| Fatura persistida por cartão/ciclo | `financeiro/models.py::Fatura`, constraint `uniq_fatura_cartao_ciclo` |
| Compra em N parcelas | `financeiro/services/cartoes_faturas.py::criar_compra_cartao` |
| Parcela futura | `financeiro/services/parcelas_futuras.py::contribuicoes_futuras` |
| OFX tolerante | `financeiro/ofx.py::OFXParser.parse`, `_parse_tolerant` |
| Reimportação | `financeiro/services/importacao_ofx.py::_chave_item`, `_conciliar_item`, `_copiar_titulos_multiplos_reimportados` |
| Pré-vínculo estrito | `financeiro/services/importacao_ofx.py::sugerir_vinculo_confiavel`, `_candidatos_vinculo_confiavel` |
| Busca manual ampla | `financeiro/services/importacao_ofx.py::buscar_candidatos_vinculo`, `escopo=TODOS` |
| Conciliação múltipla de títulos | `VinculoTituloImportacao`, `sincronizar_titulos_multiplos`, `_confirmar_vinculos_multiplos_titulo` |
| Classificação histórica | `preparar_contexto_classificacao`, `aplicar_sugestao_classificacao` |
| Conciliação de parcela | `financeiro/services/importacao_ofx.py::_confirmar_vinculo_parcela` |
| Proteção de revisados | `financeiro/services/importacao_ofx.py::aplicar_alteracoes_lote`, `ItemImportacao.revisado_em` |
| Fechamento | `financeiro/services/fechamento_faturas.py::fechar_fatura` |
| Pagamento parcial | `conciliar_pagamento`, `_atualizar_titulo` |
| Transporte | `criar_transporte`, `_confirmar_item_cartao` |
| Totais confirmado/projetado | `financeiro/services/cartoes_faturas.py::calcular_totais_parcelas`, consumido por `consultar_cartoes_faturas` e `financeiro/services/dashboard.py` |
| Aviso de ciclo | `financeiro/services/cartoes_faturas.py::aviso_ciclo_cartao`, `LancamentoForm`, `CompraCartaoForm` e `financeiro/views.py::importacao_revisao` |
| Resultado | `financeiro/services/dashboard.py::_adicionar_linha_analitica` |
| Despesas líquidas | `financeiro/services/dashboard.py::_despesas_liquidas` |
| Intervalo inclusivo | `financeiro/services/dashboard.py::_intervalo_dashboard` |
| Detalhamento consultivo | `financeiro/services/detalhamento_dashboard.py::consultar_detalhamento_dashboard` |
| Limite comprometido | `financeiro/services/dashboard.py::_limites_cartoes` |
| Privacidade visual | `templates/financeiro/dashboard.html::applyValuesVisibility` |
| Saldo | `financeiro/services/saldo_contas.py::reprocessar_saldo_conta`, `financeiro/services/dashboard.py::_saldo_contas` |
| Gastos controláveis | `dashboard::consultar_dashboard`, `_pontos_atencao` |
| Recorrência manual | `financeiro/services/lancamentos.py::criar_lancamentos_recorrentes`, `replicar_edicao_recorrencia` |
| Agrupamento por fatura | `financeiro/services/lancamentos.py::_agrupar_linhas_cartao_por_fatura` |
| Clonagem de lançamento | `financeiro/views.py::dados_clonagem_lancamento`, `lancamento_clonar` |
| Pessoa em texto livre | `financeiro/forms.py::LancamentoForm`, `EventoFinanceiro.pessoa_nome_livre`, `ParcelaCartao.pessoa_nome_livre` |
| Limpeza de observações | `financeiro/migrations/0014_remover_observacoes_automaticas_importacao.py` |
| PWA | `my_financeiro/pwa.py`, `pwa/service-worker.js`, `templates/pwa/` |

## 27. Glossário

- **Evento:** fato financeiro lógico.
- **Movimento:** representação efetiva do evento em uma conta.
- **Compra:** registro pai de uma operação no cartão.
- **Parcela:** cobrança de uma compra em determinado ciclo.
- **Fatura:** obrigação consolidada do cartão por ciclo.
- **Título:** valor a pagar/receber, previsto ou aberto.
- **Liquidação:** baixa total ou parcial de um título.
- **Conciliação:** vínculo entre OFX e registro existente/criado.
- **Chave de conciliação:** hash determinístico do item OFX e do contexto.
- **Pré-vínculo:** destino novo sugerido para revisão; não equivale a uma conciliação confirmada.
- **Série recorrente:** conjunto de ocorrências independentes materializadas na criação manual.
- **`computa_resultado`:** flag da categoria usada pelo dashboard para incluir/excluir o rateio do resultado.
- **Saldo transportado:** obrigação remanescente levada de uma fatura para outra.
- **PWA:** instalação web com manifesto e service worker; neste projeto não significa acesso aos dados financeiros offline.

## 28. Limitações e estado da entrega

Houve alterações de schema e dados durante a evolução registrada neste documento. Em especial, `0014_remover_observacoes_automaticas_importacao` corrige dados históricos, `0015_lancamentos_recorrentes` adiciona a série recorrente e `0016_vinculo_titulo_importacao` cria a persistência da conciliação múltipla de títulos. As migrations até `0015` apareciam aplicadas no ambiente consultado em 16/10; a `0016` deve ser aplicada nos ambientes que receberem esta evolução. A renomeação preexistente de índice permanece uma decisão separada para possível `0017`.

Os testes foram executados no ambiente virtual local com banco de testes preservado; os resultados estão na seção 22. Não foram executados nesta revisão:

- build/deploy e smoke test do Docker publicado;
- validação contra o PostgreSQL de produção;
- interação visual completa em navegador desktop, celular ou tablet;
- instalação e atualização real da PWA;
- queda de conexão e fallback do service worker;
- persistência de `localStorage`, modal e simulador em navegador real;
- proxy HTTPS e acesso externo publicado.

Testes Django, análise estática e `manage.py check` não substituem essas verificações. O ciclo informado continua sendo a decisão operacional; o dia de fechamento produz orientação, não realocação automática.

## 29. Registro da implementação de fatura e ciclo — 08/10/2026

### Regras consolidadas

1. `Fatura confirmada` representa somente parcelas realizadas, descontando cancelamentos, pagamentos de fatura e créditos/estornos.
2. `Fatura projetada` representa parcelas realizadas, previstas e pendentes, com as mesmas exclusões e abatimentos.
3. `Saldo transportado` permanece separado da projeção e participa apenas do `Saldo exigível` operacional.
4. `faturaAtual` permanece disponível por compatibilidade e agora significa `total_projetado`.
5. O dia de fechamento é validado de forma informativa; não altera o ciclo escolhido, o status da importação ou a confirmação.
6. Sem vencimento explícito, compra realizada até o fechamento, inclusive, sugere o ciclo de pagamento do mês seguinte; compra posterior ao fechamento sugere o ciclo de dois meses à frente. Em `N/M`, a estimativa avança ainda `N - 1` meses.
7. Não são aplicados ajustes de fim de semana, feriado ou calendário bancário.

### Interfaces atualizadas

- Dashboard: exibe `Fatura confirmada` e `Fatura projetada`.
- Cartões e faturas: exibe `Fatura confirmada`, `Fatura projetada`, `Saldo transportado` e `Saldo exigível` quando há painel de fatura.
- Compra manual: mostra aviso de ciclo sem bloquear a gravação.
- Revisão OFX: mostra aviso por item, inclusive após atualização AJAX, sem marcar o item como divergente por causa do ciclo.

### Compatibilidade preservada

- Este ajuste específico de fatura/ciclo não exigiu migration ou alteração de schema. Evoluções posteriores do projeto incluíram as migrations descritas na seção 19.
- Nenhum endpoint público foi alterado.
- `Fatura.total`, `Fatura.total_exigido`, `Titulo.saldo_aberto`, saldo, resultado financeiro e pagamento de fatura mantêm o comportamento operacional existente.
- Compras históricas não foram migradas nem realocadas.

## 30. Matriz formal do `computa_resultado` — 08/10/2026

A matriz registrada em 08/10 foi reconciliada abaixo com a aplicação atual de `computa_resultado` no dashboard.

| Operação | Resultado analítico | Saldo atual | Fluxo realizado | Saldo projetado | Fatura/limite |
|---|---:|---:|---:|---:|---:|
| Movimento realizado computável | Entra | Integral | Integral | Já refletido no saldo | Conforme regra da operação |
| Movimento realizado não computável | Não entra | Integral | Integral | Já refletido no saldo | Conforme regra da operação |
| Título futuro computável | Não realizado | Não | Não | Integral | Conforme regra da operação |
| Título futuro não computável | Não realizado | Não | Não | Não entra | Conforme regra da operação |
| Título futuro com rateio misto | Não realizado | Não | Não | Apenas proporção computável | Conforme regra da operação |
| Título futuro sem categoria/rateio | Não realizado | Não | Não | Integral | Conforme regra da operação |
| Compra/parcela de cartão | Entra conforme categoria/rateio computável | Não afeta conta imediatamente | Não afeta caixa imediatamente | Conforme fatura/título | Integral, independentemente da categoria |
| Estorno de cartão | Reduz despesa quando ligado a categoria de despesa computável | Conforme eventual movimento | Conforme eventual movimento | Conforme fatura/título | Reduz fatura, independentemente da categoria |

### Decisões registradas naquele ajuste e situação atual

- Transferências e saques serão tratados por categoria, sem rotina específica nesta etapa.
- Não será implementada associação automática de estorno à compra original.
- O ajuste de 08/10 não alterou a reimportação OFX; o comportamento atual, incluindo novo lote de auditoria sem duplicidade financeira, está consolidado na seção 6.
- A recorrência foi adiada naquele momento, mas depois foi implementada para lançamentos manuais pela migration `0015_lancamentos_recorrentes`. O indicador de orçamento no dashboard continua fora do escopo identificado.
- A ausência de alteração de modelo, migration, schema ou endpoint referia-se somente à matriz formal de 08/10; não descreve as evoluções posteriores.

## 31. Importação de compras futuras e conciliação posterior via OFX — implementação inicial de 08/10 e estado atual em 16/10/2026

### Finalidade

Compras realizadas durante o ciclo do cartão podem ser registradas antes do fechamento da fatura, mesmo quando a operadora ainda não disponibilizou o OFX. A planilha cria a previsão; o OFX posterior confirma a parcela efetivamente lançada.

### Origem e rastreabilidade

- A planilha usa o pipeline existente de `Importacao` e `ItemImportacao`.
- O adaptador do lote é `cartao_planilha`; não há tabela específica para planilhas.
- O lote possui um cartão e um ciclo inicial selecionados na tela.
- A planilha aceita XLSX e CSV, com uma linha por compra.
- A linha original permanece em `registro_original`, com chave determinística para detecção de duplicidade.
- O status `PLANEJADO` identifica uma compra futura incorporada ao sistema, sem significar que houve conciliação OFX.

### Modelo de planilha

| Coluna | Obrigatória | Regra |
|---|---:|---|
| `descricao` | Sim | Descrição ou estabelecimento, limitada ao tamanho do lançamento |
| `data_compra` | Sim | `DD/MM/AAAA`, `AAAA-MM-DD` ou data nativa XLSX |
| `valor_total` | Sim | Valor positivo, aceitando formato brasileiro |
| `quantidade_parcelas` | Sim | Quantidade positiva de parcelas |
| `categoria` | Não | Categoria ativa existente do usuário |
| `pessoa` | Não | Pessoa ativa existente do usuário |
| `ambito` | Não | Âmbito existente; vazio usa `NAO_DEFINIDO` |
| `observacao` | Não | Texto complementar |

Cartão e ciclo não são repetidos por linha. A primeira versão é exclusiva para compras/despesas e não aceita pagamento de fatura, transferência ou estorno como operação da planilha.

### Criação das previsões

Após a confirmação do lote:

1. É criado um evento de despesa `PREVISTO`.
2. É criada uma `CompraCartao` com o valor total e a chave determinística.
3. Todas as `ParcelaCartao` são criadas como `PREVISTO`, inclusive a primeira.
4. O primeiro ciclo é o informado no lote; os seguintes usam `proximo_ciclo`.
5. O valor é distribuído em centavos usando a mesma regra da compra manual.

Duplicidades por cartão, descrição normalizada, data, valor total e quantidade de parcelas ficam pendentes para decisão explícita. Não são criadas silenciosamente.

### Pré-vínculo e conciliação OFX atuais

O pré-vínculo automático usa a regra estrita compartilhada pelo fluxo de importação:

- mesma data e mesmo valor;
- destino disponível e pertencente ao usuário/contexto correto;
- para cartão, parcela do cartão e ciclo selecionados;
- quando o OFX informa `N/M`, mesma parcela e mesmo total;
- somente um candidato exato permite preencher o destino sugerido.

Mesmo com um único candidato, a correspondência não é confirmada automaticamente. O item fica `PENDENTE`, com ação `VINCULAR`, e o usuário pode manter, trocar ou remover a sugestão antes de confirmar o lote. Havendo mais de um candidato exato, nenhum destino é pré-selecionado; sem candidato, a ação inicial é criar um novo lançamento.

A busca manual é deliberadamente mais ampla. Para cartão, o escopo `Sugestões` exige a mesma data e tolera diferença de até um centavo no valor antes de ordenar por pontuação; `Buscar em todos` remove esse corte e recupera as parcelas estruturalmente elegíveis do ciclo para permitir escolha humana. Pontuação, descrição, categoria, pessoa e `N/M` ajudam a ordenar e explicar a lista, mas não substituem a regra estrita do pré-vínculo automático.

Antes da confirmação, a parcela planejada continua `PREVISTO`. Depois da confirmação do vínculo, passa a `REALIZADO`, recebe o valor efetivo, a fatura é recalculada e a evidência da liquidação é registrada. A disponibilidade do destino é revalidada no backend para impedir vínculo duplicado ou concorrente.

Reimportações de evidências já confirmadas reutilizam os vínculos pela chave de conciliação e não criam novos efeitos financeiros. O ciclo informado pelo usuário não é alterado automaticamente: aviso de fechamento não desloca compras históricas ou planejadas.

### Interfaces e compatibilidade

- A tela de importação possui fluxo separado para OFX e planilha de compras futuras.
- Há modelo CSV para download; XLSX e CSV são aceitos no upload.
- A revisão de importação permanece compartilhada entre as duas origens.
- Não há endpoint público novo.
- Não há nova tabela, campo de banco ou migration estrutural; `adaptador`, `registro_original` e o status textual existentes são reutilizados.
- `Fatura`, `CompraCartao`, `ParcelaCartao`, fechamento e limite de cartão preservam suas regras atuais.

### Testes registrados

Os testes atuais cobrem leitura XLSX/CSV, valores brasileiros, validação de categoria, parcelamento entre anos, duplicidade, pré-vínculo estrito, ambiguidade, busca ampla, troca manual do destino, revalidação na confirmação e reimportação sem novo efeito financeiro. Na verificação de 16/10/2026, as suítes de serviço de importação e planilha somaram 71 testes aprovados.

## 32. PWA e contingência offline — 14/10/2026

### Instalação e identidade

O projeto expõe `manifest.webmanifest`, ícones de 180, 192 e 512 pixels e um service worker no escopo raiz. O manifesto usa modo `standalone` e oferece atalhos para novo lançamento, lançamentos e cartões/faturas. O frontend exibe a ação de instalação apenas quando o navegador fornece `beforeinstallprompt`.

Service workers e instalação dependem de contexto seguro. Em desenvolvimento, `localhost` é aceito; em acesso por IP ou domínio, deve ser usada uma origem HTTPS válida. O `docker-compose.yml` publica a aplicação, mas não termina TLS por si só.

### Política de cache

O cache é intencionalmente restrito ao shell público seguro:

- página `/offline/`;
- manifesto;
- ícones da aplicação.

Navegações usam estratégia de rede com fallback para a página offline. Telas autenticadas, respostas financeiras, formulários e dados do usuário não são armazenados para consulta ou edição offline. Também não existe fila de sincronização, escrita offline, push ou replicação posterior de lançamentos.

### Atualização e limites da evidência

Ao ativar uma nova versão, o service worker remove caches antigos com o prefixo da aplicação e assume os clientes abertos. Os seis testes automatizados da PWA validam rotas, manifesto, ícones, registro básico e a presença da lógica de fallback no JavaScript servido, mas não simulam uma queda real de conexão nem comprovam instalação, atualização do service worker ou compatibilidade específica de navegador/dispositivo.

Essa implementação não altera modelos financeiros, banco de dados ou regras de cálculo.
