# My app financeiro — diagnóstico e projeto inicial

## 1. O que os arquivos permitem concluir

Foram analisados os 15 arquivos enviados. Os três Excel foram usados como base da análise inicial da conta, pois preservam melhor os históricos complementares. Para a implementação do aplicativo, o formato de importação definido é exclusivamente OFX, tanto para extratos de conta corrente quanto para faturas de cartão de crédito. Os TXT, CNAB 240 e BANCOOB 500 foram conferidos por data, valor e multiplicidade de movimentos contra os Excel: os 122 movimentos realizados conferem. Há também três movimentos futuros. Cada formato é uma representação do mesmo extrato; não se somam os quatro arquivos de cada mês.

Os três OFX contêm 292 registros, incluindo pagamento da fatura anterior, créditos, tarifas e parcelas. O relatório de consumo por cartão exclui os pagamentos anteriores e desconta os demais créditos. Os pagamentos na conta aparecem somente no fluxo de caixa. As parcelas pertencem à fatura importada, ainda que a data da compra seja de meses anteriores.

O titular informado é L.MACHADO CONSULTORIA E TECNOLOGIA LTDA. Essa conta reúne recebimentos de empresas e pagamentos de natureza ainda não identificada. O saldo de caixa pode ser apurado; o custo pessoal total e a renda pessoal disponível dependem de separar pessoal, profissional e transferências. O app deve permitir essa separação em cada lançamento.

**Recorte de outubro:** o extrato emitido em 04/10 contém dois movimentos em 05/10, na seção de lançamentos realizados. Eles foram mantidos como apresentados pelo banco. Há ainda débitos futuros para 07, 13 e 15/10. Outubro é parcial e não deve ser comparado como mês completo aos demais.

### Conta corrente — fluxo de caixa

| Período | Saldo inicial | Entradas | Saídas totais | Pagamento do cartão | Outras saídas | Saldo final |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08 | R$ 5.151,23 | R$ 31.661,26 | R$ 34.715,05 | R$ 8.176,71 | R$ 26.538,34 | R$ 2.097,44 |
| 2026-09 | R$ 2.097,44 | R$ 37.266,91 | R$ 38.258,74 | R$ 8.836,37 | R$ 29.422,37 | R$ 1.105,61 |
| 2026-10 | R$ 1.105,61 | R$ 0,00 | R$ 1.358,81 | R$ 0,00 | R$ 1.358,81 | R$ -253,20 |

Em agosto e setembro juntos, as saídas excederam as entradas em **R$ 4.045,62**. Isso explica a redução do saldo de R$ 5.151,23 para R$ 1.105,61. Outras saídas incluem PIX, boletos, empréstimos, seguros, tarifas e saque; não são automaticamente despesas pessoais. Saque deve transferir saldo para uma carteira de dinheiro, cujos gastos serão registrados depois.

### Cartão — faturas de agosto, setembro e outubro

| Fatura | Débitos no OFX | Créditos/estornos | Fatura pelos lançamentos | Saldo informado no OFX | Diferença | Débitos com parcela |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08 | R$ 8.437,62 | R$ 260,91 | R$ 8.176,71 | R$ 8.134,59 | R$ 42,12 | R$ 1.545,65 |
| 2026-09 | R$ 8.851,87 | R$ 15,50 | R$ 8.836,37 | R$ 8.829,57 | R$ 6,80 | R$ 2.831,19 |
| 2026-10 | R$ 8.553,69 | R$ 15,50 | R$ 8.538,19 | R$ 8.528,17 | R$ 10,02 | R$ 3.091,61 |

As faturas somam **R$ 25.551,27**, média de **R$ 8.517,09**. Os R$ 8.176,71 de agosto e R$ 8.836,37 de setembro conferem com os débitos DBAUTO VIS da conta. Os R$ 8.538,19 de outubro conferem com o débito futuro em 13/10. O campo BALAMT do OFX não coincide com a cobrança reconciliada. Não criar um ajuste de despesa para eliminar essa diferença: preservá-la na conferência e usar o total reconciliado dos lançamentos.

O pagamento anterior dentro de cada OFX não é um estorno de compras atuais nem uma receita. A identificação do ciclo usa arquivo, sequência de parcelas e conciliação com a conta. DTSTART e DTEND informam a data da exportação em todos os OFX e não delimitam corretamente a fatura. DTASOF é 02/08, 31/08 e 01/10, respectivamente. Confirmar os dias habituais de fechamento e vencimento no cadastro do cartão.

### Categorias sugeridas do cartão

Valores líquidos das três faturas. Inferência pelo nome do estabelecimento, sujeita a revisão. Mercado pode incluir itens de casa; clube pode incluir consumo; farmácia pode incluir produtos diversos. Não é possível conhecer o item comprado pelo extrato.

| Categoria sugerida | Total nas três faturas | Média por fatura |
| --- | --- | --- |
| Mercado e alimentação | R$ 4.468,30 | R$ 1.489,43 |
| A classificar | R$ 3.250,85 | R$ 1.083,62 |
| Alimentação fora | R$ 3.204,24 | R$ 1.068,08 |
| Saúde e farmácia | R$ 2.531,19 | R$ 843,73 |
| Tecnologia e assinaturas | R$ 1.870,58 | R$ 623,53 |
| Combustível | R$ 1.835,16 | R$ 611,72 |
| Vestuário e compras | R$ 1.625,67 | R$ 541,89 |
| Lazer e clube | R$ 1.470,18 | R$ 490,06 |
| Casa e manutenção | R$ 1.279,61 | R$ 426,54 |
| Eletrônicos | R$ 1.260,00 | R$ 420,00 |
| Telefonia e internet | R$ 1.086,59 | R$ 362,20 |
| Pets | R$ 529,94 | R$ 176,65 |
| Pedágio e mobilidade | R$ 432,52 | R$ 144,17 |
| Educação e investimentos | R$ 388,40 | R$ 129,47 |
| Suplementos | R$ 259,10 | R$ 86,37 |
| Tarifas e impostos | R$ 58,94 | R$ 19,65 |

Há **R$ 3.250,85 (12.7%)** a classificar. Todas as demais categorias são sugestões, não confirmação do uso pessoal. Saúde, empréstimo do carro e plano de saúde precisam de classificação cuidadosa: o extrato identifica contratos de empréstimo 00503768 e 00503206, mas não sua finalidade. Os boletos genéricos não permitem localizar o plano de saúde com segurança.

### Principais estabelecimentos do cartão

| Descrição agrupada | Total cobrado |
| --- | --- |
| COMPER 108 RONDONOPOLIS | R$ 2.912,79 |
| SPLENDORE FARMACI | R$ 1.988,75 |
| CAICARA CLUBE RONDONOPOLIS | R$ 1.292,86 |
| VIDEOSOM CELULARES | R$ 1.260,00 |
| POSTO KIMURA JUSCIMEIRA | R$ 734,80 |
| AcougueSantaFe RONDONOPOLIS | R$ 595,06 |
| AUTO POSTO URSAO III RONDONOPOLIS | R$ 589,30 |
| ZAHER E CIA LTDA | R$ 528,58 |
| AgroJunior | R$ 456,38 |
| GONCALVES SUPERMERCA RONDONOPOLIS | R$ 399,34 |
| ALO PIZZA RONDONOPOLIS | R$ 394,00 |
| R A CONVENIENCIA LTD RONDONOPOLIS | R$ 386,00 |
| WEST COUNTRY | R$ 372,00 |
| TIM POSV RIO DE JANEIR | R$ 358,84 |
| R A ROCHA E CIA LTDA | R$ 347,88 |

O agrupamento acima remove espaços extras e o marcador de parcela. Variações de nome e sufixos podem manter um mesmo estabelecimento em mais de uma linha; o cadastro de aliases do app resolverá isso. Valores parcelados são o que foi cobrado nessas faturas, não o valor integral da compra.

### Parcelas e próximos compromissos

Em outubro, **R$ 3.091,61** estão em linhas com marcador de parcela, incluindo R$ 15,50 de anuidade compensada por desconto. Excluindo essa anuidade, há R$ 3.076,11 de parcelas de compras e serviços. O marcador 02/12 de Livelo pode representar um contrato recorrente: manter a previsão e confirmar sua natureza.

Após outubro, as parcelas identificadas representam **R$ 3.414,73**, estimados por valor atual × quantidade restante. Arredondamentos, antecipações, cancelamentos ou contratos recorrentes podem alterar o valor.

| Fatura projetada | Parcelas já conhecidas |
| --- | --- |
| 2026-11 | R$ 2.135,36 |
| 2026-12 | R$ 611,32 |
| 2027-01 | R$ 347,03 |
| 2027-02 | R$ 65,06 |
| 2027-03 | R$ 42,66 |
| 2027-04 | R$ 42,66 |
| 2027-05 | R$ 42,66 |
| 2027-06 | R$ 42,66 |
| 2027-07 | R$ 42,66 |
| 2027-08 | R$ 42,66 |

Essa projeção inclui apenas parcelas remanescentes da fatura de outubro. Não inclui novas compras, assinaturas sem marcador de parcela, empréstimos e demais contas. Se nada novo for parcelado, a parcela mensal conhecida cai de R$ 2.135,36 em novembro para R$ 611,32 em dezembro.

Débitos previstos na conta:

| Data | Documento | Descrição | Valor |
| --- | --- | --- | --- |
| 2026-10-07 | 00503206 | DÉB.EMPRÉSTIMO | R$ 146,36 |
| 2026-10-13 | DBAUTO VIS | DÉB.CONV.DEMAIS EMPRESAS | R$ 8.538,19 |
| 2026-10-15 | TOKIO SEGU | DÉB. CONV. SEGUROS | R$ 273,95 |

Total previsto: **R$ 8.958,50**. Partindo do saldo de **R$ -253,20** informado em 05/10, sem novas entradas ou saídas, o saldo após esses três débitos seria **R$ -9.211,70**. Necessidade de entradas para cobri-los e zerar o saldo: **R$ 9.211,70**. O limite de cheque especial não é saldo próprio e deve aparecer separado.

### Por onde começar a reduzir gastos

1. **Revisar alimentação fora.** A sugestão totaliza R$ 3.204,24 nas três faturas. Uma meta experimental de reduzir 20% dessa média representaria cerca de R$ 213,62 por fatura. Esse é um cenário, não economia já obtida. Conveniências podem conter compras de mercado e precisam de revisão.
2. **Revisar assinaturas e serviços digitais.** A categoria sugerida soma R$ 1.870,58. Há OpenAI, Google, Hostgator, Contabo, AWS, Base44, Meli+ e Prime. Separar ferramentas de trabalho de serviços pessoais e verificar uso e cobranças recorrentes. Parcelas de hospedagem não são compras novas a cada mês.
3. **Limitar novos parcelamentos.** Exibir antes de confirmar uma compra quanto ela acrescenta a cada fatura futura. O ganho imediato é impedir que o comprometimento cresça enquanto as parcelas atuais terminam.
4. **Classificar PIX e boletos de maior valor.** Na conta, a maior parte das saídas ainda está sem finalidade identificada. Resolver essa fila é necessário antes de concluir onde está o principal desperdício ou definir uma meta pessoal global.

## 2. Proposta do aplicativo

### Experiência principal

Aplicativo web responsivo, pensado primeiro para o computador. A abertura mostra mês, contas selecionadas, saldo próprio, próximos vencimentos e despesas por categoria. Alternar entre **Caixa** (quando o dinheiro entrou/saiu) e **Faturas** (o que compõe o cartão). Não misturar os dois em um total.

| Tela | O que fazer |
| --- | --- |
| Visão geral | Ver entradas, saídas, saldo, fatura atual, próximos débitos e gastos por categoria. Filtrar pessoal, profissional ou todos. |
| Lançamentos | Buscar por descrição, pessoa, categoria, conta, período e situação. Registrar receita/despesa, dividir um gasto entre categorias e alterar classificação. |
| Cartões e faturas | Ver compras e parcelas por ciclo, fechar/reabrir fatura com histórico, programar pagamento e conciliar débito da conta. |
| Parcelas | Ver compra original, parcela atual/total, saldo a pagar e calendário dos próximos meses. |
| Recebíveis e contas a pagar | Cadastrar previsão com pessoa, categoria, conta e vencimento. Conciliar recebimento/pagamento real com a previsão. |
| Importar e revisar | Enviar arquivo, conferir conta/cartão e ciclo, ver novos/duplicados/pendências e confirmar o lote. Corrigir categorias em grupo. |
| Cadastros e regras | Contas, carteiras, cartões, categorias, pessoas, aliases e regras aprendidas com a classificação. |

A prévia HTML entregue permite explorar os dados, filtrar por conta e cartão e testar os CRUDs de lançamentos, contas financeiras, cartões e categorias na sessão. Não possui servidor, banco de dados, importação definitiva ou pagamento bancário. Alterações são perdidas ao recarregar. É uma referência visual para a implementação.

### Regras que evitam distorções

- **Conta, cartão e categoria são campos diferentes.** Categoria descreve a finalidade; conta/cartão define a origem; pessoa identifica quem recebeu/pagou; âmbito define pessoal/profissional/não definido.
- **Compra no cartão:** registra despesa e obrigação da fatura. Não reduz saldo da conta corrente nesse momento.
- **Fechamento:** consolida os itens do ciclo e gera um único título a pagar vinculado à fatura, com vencimento e conta de pagamento. Não gera outra despesa nem faz um débito bancário. Não executar pagamento automaticamente no MVP.
- **Pagamento da fatura:** reduz saldo da conta e dívida do cartão. Vincular o débito DBAUTO VIS ao título existente. A entrada de pagamento no OFX representa o mesmo pagamento. Registrar um único evento de liquidação com evidências nos dois arquivos.
- **Pagamento parcial:** conservar o saldo aberto. Juros, IOF e outras tarifas entram separadamente quando informados. Não declarar quitada por existir um pagamento.
- **Estorno:** reduz gasto e dívida; vincular à compra quando identificável. Preservar bruto, crédito e líquido.
- **Parcelamento:** uma compra original tem N parcelas. O OFX registra apenas a parcela do ciclo. Previsões futuras não são realizadas; quando a parcela efetiva chegar, substituir/conciliar a previsão, sem duplicá-la.
- **Compra antiga:** inferir grupo por cartão, data original, estabelecimento, total de parcelas e sequência. Valores podem variar um centavo. Se houver duas compras iguais, solicitar revisão em vez de unir silenciosamente.
- **Transferência e saque:** dois lados de um mesmo movimento patrimonial. Não contabilizar como consumo ou renda. Um saque alimenta a carteira de dinheiro.
- **Empréstimo:** mostrar saída integral no caixa; separar principal, juros e encargos quando houver contrato/demonstrativo. Não inventar composição pelo extrato.
- **Recebível:** previsão não é dinheiro recebido. Fazer baixa vinculada ao crédito real, permitindo recebimentos parciais e diferenças.
- **Pessoal e profissional:** reportar separadamente; recebimento de cliente na conta da empresa não é automaticamente salário ou renda pessoal.
- **DDA:** extrato comprova débito realizado. Um boleto apenas apresentado no DDA é uma conta prevista, que exige arquivo ou cadastro específico.

### Importação exclusivamente por OFX

**O aplicativo utilizará sempre arquivos OFX para importar extratos de conta corrente e faturas de cartão de crédito.** Excel, TXT, CNAB 240 e BANCOOB 500 permanecem apenas como fontes históricas desta análise; não serão formatos de importação do aplicativo. Lançamentos manuais continuarão disponíveis pelos formulários.

| Arquivo | Origem no aplicativo | Regras |
| --- | --- | --- |
| OFX de extrato de conta corrente | Conta financeira cadastrada | Identificar instituição e conta, preservar sinais e histórico, importar os movimentos efetivos e conferir saldo e período quando informados. |
| OFX de fatura de cartão de crédito | Cartão cadastrado e ciclo de fatura | Identificar cartão, confirmar ciclo, separar compras, parcelas, créditos e pagamentos anteriores e conferir a composição da fatura. |

Rotina: exportar o **OFX do extrato da conta** e o **OFX da fatura do cartão**, enviar os arquivos, confirmar os cadastros correspondentes e revisar a conciliação antes de confirmar a importação. Não converter esses arquivos para Excel.

O conjunto inicial contém OFX de cartão, mas não contém OFX da conta corrente. O adaptador de conta deverá ser validado com um arquivo real desse banco. Não presumir que o OFX contenha débitos futuros ou boletos DDA apenas apresentados: quando esses dados não estiverem no arquivo, deverão ser cadastrados como previsões manuais. As limitações de datas e saldo observadas nos OFX de cartão permanecem registradas no diagnóstico.

Pipeline: carregar OFX → identificar instituição e origem → selecionar/confirmar conta ou cartão e ciclo → normalizar os registros → **conciliar obrigatoriamente com os lançamentos existentes e suas identificações de importação** → conferir totais e saldo → sugerir categorias e vínculos → revisar pendências → confirmar o lote em uma transação → manter histórico e permitir desfazer o lote preservando conciliações dependentes.

### Conciliação obrigatória em importações repetidas

Toda importação deve comparar os registros recebidos com os lançamentos já existentes, especialmente os anteriormente identificados por importação. Isso vale para o reenvio do mesmo arquivo, uma nova exportação do mesmo período, períodos sobrepostos e uma fatura atualizada. **Um lançamento reconhecido deve ser conciliado com o registro existente; nunca inserido novamente como outro lançamento.**

- **Identificação e rastreabilidade:** guardar instituição, conta/cartão, ciclo quando aplicável, FITID ou identificador externo, ocorrência, dados originais do registro e vínculo entre item importado e lançamento. A conciliação reutiliza esse vínculo. O mesmo lançamento pode ter evidências em mais de um lote sem duplicar o evento financeiro.
- **Arquivo idêntico:** o hash identifica o reenvio. Reutilizar o lote e seus vínculos, informar que os registros já foram importados e apresentar a conferência sem criar novos lançamentos ou reaplicar baixas.
- **Conta corrente:** usar instituição + conta + FITID/identificador externo, quando confiável. Na ausência de identificação suficiente, comparar data, valor com sinal, documento, histórico e quantidade de ocorrências. Documento genérico como “Pix” não é uma chave única. Movimentos legítimos de mesma data e valor devem permanecer distintos.
- **Cartão:** FITID isolado não basta, pois neste conjunto ele se repete entre ciclos para parcelas distintas. Usar instituição + cartão + fatura/ciclo + FITID + ocorrência; conciliar a compra original e a sequência da parcela separadamente. Parcelas de ciclos diferentes não são duplicidades.
- **Já existente e sem diferença:** manter o lançamento e associar a evidência da nova importação. Preservar categoria, pessoa, âmbito, observações, rateios e demais ajustes feitos pelo usuário.
- **Já existente com diferença:** apresentar a divergência para revisão antes de atualizar valores, datas, descrições ou vínculos financeiros. Uma alteração no valor de um registro identificado não autoriza criar um segundo lançamento para contornar o conflito.
- **Registro novo:** criar apenas após a conciliação confirmar que não corresponde a lançamento existente, previsão ou parcela já cadastrada.
- **Lançamento manual ou previsto correspondente:** sugerir o vínculo com o registro do OFX. Após confirmação, associar a identificação de importação ao lançamento existente e realizar sua baixa quando cabível, sem duplicá-lo.
- **Pagamento da fatura:** conciliar o débito da conta com o pagamento apresentado no OFX do cartão e com a obrigação já registrada. As evidências dos dois arquivos representam uma única liquidação, que não pode ser aplicada duas vezes.
- **Correspondência ambígua:** manter pendência de revisão; não unir, excluir ou duplicar automaticamente registros que possam representar movimentos distintos.
- **Ausência em nova exportação:** não excluir nem estornar automaticamente um lançamento antigo por não constar em um OFX posterior ou de período menor.

A revisão deve apresentar quantidades e valores de **novos**, **já conciliados**, **divergentes** e **pendentes**, além dos vínculos com os registros existentes. Reimportar sem alterações deve produzir zero novos lançamentos e conservar saldos, totais de fatura e liquidações. Correções bancárias e estornos devem ser tratados com rastreabilidade, sem apagar o histórico.

## 3. Referência de campos para lançamentos manuais

O modelo Excel elaborado anteriormente permanece apenas como referência de campos e exemplos para os formulários de lançamentos manuais. A importação por Excel deixa de fazer parte do escopo: todo arquivo importado pelo aplicativo será OFX. A planilha existente não é alterada por esta atualização do documento.

Campos mínimos: `data`, `descricao`, `valor`, `tipo`, `origem` e o identificador da conta ou cartão. Nos formulários manuais, o valor é positivo e o tipo define entrada/saída. Os adaptadores OFX preservam os sinais originais dos movimentos.

| Campo | Regra |
| --- | --- |
| id_externo | Identificador do banco ou referência manual, tratado como texto. Pode repetir entre ciclos de cartão. |
| data | Data original da compra/movimento. Data Excel ou DD/MM/AAAA. |
| descricao | Histórico legível. Preservar o original na importação. |
| valor | Número positivo em BRL. Em PARCELA, valor da parcela, nunca da compra inteira. |
| tipo | DESPESA, RECEITA, ESTORNO, PAGAMENTO_FATURA ou TRANSFERENCIA. |
| origem | CONTA ou CARTAO. |
| conta | Código cadastrado; obrigatório para origem CONTA. |
| cartao | Código cadastrado; obrigatório para origem CARTAO. |
| categoria | Opcional; desconhecida fica pendente. |
| pessoa | Pagador/beneficiário; opcional até a revisão. |
| ambito | PESSOAL, PROFISSIONAL ou NAO_DEFINIDO. |
| situacao | REALIZADO ou PREVISTO. Cartão significa cobrança observada ou prevista, não quitação bancária. |
| vencimento | Data prevista de recebimento/pagamento; não substituir data original. |
| fatura | AAAA-MM do ciclo, obrigatório em origem CARTAO e em PAGAMENTO_FATURA. |
| modo | MOVIMENTO, PARCELA ou COMPRA_TOTAL. |
| parcela | Número da parcela quando modo PARCELA. |
| total_parcelas | Total, obrigatório em PARCELA ou COMPRA_TOTAL. |
| id_compra | Chave estável para unir parcelas da mesma compra. |
| conta_destino | Obrigatória em transferência entre contas/carteiras. |
| observacao | Complemento opcional. |

PARCELA: registro de uma parcela já cobrada; fatura obrigatória e sequência 1 ≤ parcela ≤ total. COMPRA_TOTAL: cadastro de nova compra parcelada, valor integral, data e primeira fatura obrigatórios. O app divide em parcelas, distribui centavos para manter o total e projeta os ciclos seguintes; a tela de revisão confirma o calendário. Não registrar o total e as parcelas cobradas como despesas independentes; ao importar o OFX, conciliar as parcelas com as previsões existentes. Em estorno, origem e referência permitem aplicar o crédito correto; não gerar receita pessoal. Em PAGAMENTO_FATURA, conta e cartão são obrigatórios e o movimento é uma liquidação. Em TRANSFERENCIA, conta de origem e destino distintas são obrigatórias.

## 4. Estrutura técnica recomendada

**Django + PostgreSQL, com páginas renderizadas no servidor.** Um único projeto concentra telas, regras, importadores, autenticação e relatórios; evita manter uma API e um front-end separados. CSS responsivo e JavaScript pontual bastam para a primeira versão. Django suporta PostgreSQL e traz acesso ao banco e estrutura web integrada. Documentação oficial: https://www.djangoproject.com/start/ e https://docs.djangoproject.com/en/5.2/ref/databases/ . Essa é a recomendação de projeto, não uma aplicação já instalada.

PostgreSQL local ou no mesmo servidor da aplicação; valores em NUMERIC(14,2) ou centavos inteiros, nunca float; índices por usuário/conta/data e cartão/fatura. Consultas pequenas, conexão reaproveitada e índices têm mais impacto na experiência que trocar de banco. Docker Compose com app e banco facilita instalar no computador ou servidor. Usar login, backups automáticos e restauração verificável. Nenhuma integração bancária online é necessária para o MVP.

| Entidade | Conteúdo e relações |
| --- | --- |
| conta | Banco, agência, conta, carteira, titular, tipo, saldo inicial/data; limite separado. |
| cartao | Nome, identificador externo e finais conhecidos, regra de fechamento/vencimento, conta padrão de pagamento. Troca de plástico não cria uma nova dívida se o banco mantém o mesmo contrato. |
| categoria | Grupo/subcategoria, receita/despesa, ativa. |
| pessoa | Cliente, beneficiário, nome e documento quando conhecido. |
| importacao / item_importacao | Arquivo OFX, hash, instituição, conta/cartão, ciclo, FITID/identificador externo, ocorrência, adaptador/versão, registro original, situação de conciliação e vínculo com o lançamento existente ou novo. Reimportações preservam os vínculos e não duplicam eventos. |
| evento_financeiro | Natureza, descrição, datas, valor, pessoa, âmbito e origem; suportar rateio em categorias. |
| movimento_conta | Conta, valor com sinal, data efetiva, evento e evidência importada. |
| compra_cartao / parcela | Compra original, estabelecimento, valor total conhecido/estimado, quantidade, parcela atual, valor e fatura. |
| fatura / item_fatura | Cartão, ciclo, fechamento, vencimento, bruto, créditos, total, situação e itens cobrados. |
| titulo | Receber/pagar, previsto, vencimento, saldo aberto, conta e fatura opcional. Uma fatura tem no máximo um título ativo. |
| liquidacao | Título, movimento bancário, valor, data e evidências do cartão; suporta parcial. |
| regra_categoria / orcamento | Regra por pessoa/alias/texto e limites mensais por categoria/âmbito. |

Restrições essenciais: usuário proprietário em todas as consultas; fatura única por cartão/ciclo; parcela única por compra/sequência; item de importação único por lote/ocorrência; uma mesma evidência bancária não pode liquidar duas vezes; status da fatura derivado do valor liquidado. Fechamento e confirmação de lote devem ser transacionais. Reabrir uma fatura paga exige tratar os vínculos e manter auditoria.

Relatórios: caixa por conta; despesas por categoria e estabelecimento; composição de fatura; parcelas futuras; previstos × realizados; entradas por pagador/categoria; pessoal × profissional; orçamento × gasto. Cada relatório informa sua base: caixa, fatura ou data de compra. Data de compra só deve mostrar o total integral quando a compra original for conhecida; não atribuir todas as parcelas históricas ao mês original como se fossem compras distintas.

## 5. Ordem de implementação

1. Cadastros de contas/cartão/categorias/pessoas; importação exclusivamente por OFX de conta corrente e cartão, com validação dos adaptadores; conciliação obrigatória, revisão de divergências e relatórios básicos.
2. Compra e parcela vinculadas, faturas, fechamento e título, conciliação do pagamento da conta e projeção dos próximos ciclos.
3. Recebíveis, despesas previstas/recorrentes, orçamentos e comparação previsto × realizado.
4. Aprimoramentos dos adaptadores OFX por instituição e exportação de relatórios. Não incluir importadores Excel, TXT, BANCOOB 500 ou CNAB 240.

Aceite mínimo: reimportar o mesmo OFX, uma nova exportação do mesmo período ou períodos sobrepostos não duplica movimentos; lançamentos identificados em importações anteriores são conciliados com seus registros existentes; classificações e ajustes do usuário são preservados; divergências ficam pendentes de revisão; duas parcelas com mesmo FITID em faturas distintas permanecem; dois PIX legítimos iguais não desaparecem; soma inicial + entradas − saídas confere com o saldo; fechamento não duplica despesas; baixa parcial deixa dívida aberta; parcela prevista é conciliada ao importar a efetiva; recebível não vira saldo antes de ser recebido.

Antes de carregar como base pessoal definitiva, resolver: finalidade dos dois contratos de empréstimo; beneficiários dos boletos e PIX principais; quais gastos digitais são profissionais; qual cobrança é plano de saúde; fechamento/vencimento habituais; nome/finais atuais do cartão e possíveis adicionais. Esses dados podem ser completados na fila de revisão do app.


## 6. CRUDs demonstráveis e filtros da prévia revisada

A primeira prévia não mostrava os formulários de cadastro. A revisão inclui no menu **Contas financeiras**, **Cadastro de cartões** e **Categorias**, além do botão **Novo lançamento** em Visão geral e Lançamentos. Cada cadastro contém listagem, busca, filtro de situação, formulário de inclusão/edição, ativação/inativação e exclusão. Os lançamentos têm inclusão, listagem filtrada, edição e exclusão com confirmação.

| CRUD | Campos e comportamento |
| --- | --- |
| Lançamento manual | Descrição, tipo (despesa, receita, estorno/crédito ou pagamento da fatura), data, valor, origem, conta/cartão, categoria, pessoa, âmbito, situação, vencimento, ciclo e parcelas. Receitas são lançadas na conta; devoluções no cartão usam estorno. Previsto não altera saldo próprio. |
| Conta financeira | Nome, banco/instituição, tipo (corrente, poupança, carteira em dinheiro ou conta de pagamento), agência, número, titular, âmbito, saldo inicial, data do saldo, limite de cheque especial e situação. Saldo inicial pode ser negativo; limite é separado do saldo próprio. |
| Cartão | Nome, emissor, últimos quatro dígitos opcionais, conta padrão de pagamento, dia de fechamento, dia de vencimento, limite e situação. Os dias habituais do cartão enviado continuam a confirmar. |
| Categoria | Nome, tipo (receita, despesa ou ambos), categoria superior opcional e situação. A hierarquia bloqueia ciclos. Renomear atualiza as referências dos lançamentos na sessão. |

**Incluir:** usar Novo lançamento, Nova conta, Novo cartão ou Nova categoria, preencher e salvar. **Consultar:** listagem, busca e filtros. **Editar:** ação Editar abre o formulário com os dados atuais. **Excluir:** ação Excluir abre confirmação. Conta/cartão/categoria com vínculos não pode ser excluído; usar Inativar. Inativos continuam no histórico e nos filtros, mas deixam de aparecer como opção para novos lançamentos (continuam disponíveis para editar seus registros já existentes).

### Lançamentos parcelados

Ao cadastrar uma nova despesa de cartão com mais de uma parcela, o valor informado é o **total da compra**. A prévia divide o total em centavos entre os ciclos, associa todas as parcelas à compra e marca as próximas como previstas. Exemplo: R$ 100,00 em três parcelas gera R$ 33,34, R$ 33,33 e R$ 33,33. O primeiro ciclo e a situação da primeira parcela são escolhidos no formulário. Editar uma parcela existente altera apenas o registro selecionado; não recria as demais.

Pagamento de fatura é lançado na conta e vinculado ao cartão/ciclo. Ele é uma saída de caixa e não entra na soma de consumo do cartão. A conciliação completa com o título da fatura continua prevista para o app com banco de dados; a prévia não efetua pagamentos nem fecha faturas.

### Filtros de conta e cartão

Os filtros **Conta financeira** e **Cartão de crédito** aparecem em Visão geral, Lançamentos, Cartões e faturas e Parcelas futuras. Selecionar uma conta limita os movimentos dessa conta e os cartões cuja conta de pagamento corresponde a ela. A seleção de cartões é atualizada; um cartão incompatível com a conta escolhida deixa de estar selecionado.

Na **Visão geral**, o filtro de conta controla entradas, saídas, saldo e próximos débitos. O filtro de cartão controla fatura, categorias e parcelas; ele não reduz o saldo da conta a um suposto saldo do cartão. Na tela **Lançamentos**, selecionar um cartão mostra seus itens e os pagamentos vinculados a ele na conta. Os filtros de origem, categoria, situação, busca e período se combinam com conta/cartão. Valores da conta e do cartão não são somados como despesas independentes.

Os novos registros atualizam os indicadores da sessão. Um recebível previsto aparece como previsão e só altera o saldo se editado para realizado. Saldo próprio considera saldo inicial/data e movimentos realizados. Um cartão novo passa a integrar os filtros e o formulário de compras. Novos ciclos cadastrados passam a aparecer no seletor de período.

### Limite desta prévia

Os CRUDs são demonstráveis em um HTML local: os dados ficam em memória durante a sessão. Recarregar restaura a base original. Não há persistência em banco, importação de novos arquivos, fechamento/baixa automática de fatura ou trilha de auditoria durável. Essas regras e telas orientam a implementação posterior com PostgreSQL. O teste dos fluxos verificou cálculos e ações em execução JavaScript com DOM simulado; a renderização em navegador não foi validada automaticamente neste ambiente.
