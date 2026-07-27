# Estrutura das planilhas de Trocas e Defeitos

O sistema substitui o controle manual feito em duas planilhas Google Sheets (exportadas como CSV na raiz de `work2/`). Cada linha representa **um item reclamado** — a mesma cliente aparece em várias linhas quando reclama de mais de um produto (mesmo telefone/CPF, mesma data), ou seja, a planilha mistura os conceitos de *reclamação* (atendimento) e *item da reclamação*.

- `PLANILHA TROCAS E DEFEITOS KODI.xlsx - Reclamações_Trocas 2025.csv` — marca **KODI** (esmaltes, bases, preparadores). 15 linhas.
- `PLANILHA TROCAS E DEFEITOS STALEKS.xlsx - 2026 Reclamações.csv` — marca **STALEKS** (alicates e ferramentas de manicure, sobrancelha, cílios). 86 linhas. Versão mais evoluída: tem colunas extras de logística (pedidos, reverso, rastreio).

## Colunas

| Coluna | KODI | STALEKS | Descrição / valores observados |
|---|---|---|---|
| CÓDIGO / CÓD | sim | sim | Sequencial da linha (id manual). |
| NOME DO CLIENTE | sim | sim | Nome livre. Na STALEKS carrega anotações no próprio campo: "(não encontrada)", "(sem foto)". |
| TELEFONE | sim | sim | Formato livre e inconsistente ("54 999823566", "(11) 95864-3644"). |
| CPF | sim | sim | Formato livre, com e sem pontuação, alguns truncados. |
| ESTADO | sim | sim | UF. |
| SKU | sim | sim | Código ou nome do produto. Muito inconsistente na KODI ("No Bacteria'", "no bacteria", "ULTRABOND", códigos numéricos); na STALEKS predominam códigos (PLN-10-7, TE-10-5, 20103293). |
| SGMENTO / SEGMENTO | sim (com typo) | sim | Categoria do produto. KODI: PREPARADOR, BASE, ESMALTE. STALEKS: Manicure, Sobrancelha, Cílios. |
| QUANTIDADE | sim | sim | Quantidade do item. |
| DATA RECLAM. | sim | sim | Data da reclamação (dd/mm/aaaa, inconsistente). |
| DATA COMPRA. / DATA COMPRA | sim | sim | Data da compra original. |
| PROBLEMA APRESENTADO | sim | sim | Motivo. Valores: DANIFICADO, ADAPTAÇÃO/MODELO ERRADO, NÃO RECEBEU, SEM AFIAÇÃO/PRECISÃO, DEFEITO, OXIDAÇÃO, QUEBRA DA FERRAMENTA, CANCELADO, EXTRAVIADO. |
| SOLUÇÃO | sim | sim | Resolução dada: TROCA PELO MESMO MODELO/ITEM, TROCA POR OUTRO MODELO/ITEM, ENVIO DE PEÇA, REEMBOLSO, 50% OFF, 100% OFF, VOUCHER. |
| TIPO DE FRETE | sim | sim | FRETE GRÁTIS ou FRETE PAGO. |
| VALOR DO/DE FRETE | sim | sim | Valor em R$ (texto, "R$ 24,60"). Pouco preenchido. |
| STATUS | sim | sim | KODI só usa FINALIZADO (e vazio). STALEKS: EM ABERTO, EM PROCESSO, AGUARDANDO RECEBIMENTO, FINALIZADO. Vazio = não iniciado/indefinido. |
| LOCAL DA COMPRA | sim | sim | Canal de venda: SITE KODI, SITE STALEKS, SAC, BEAUTY SHOW, MERCADOLIVRE, SHOPEE, PANDORA e revendedores diversos (texto livre). |
| OBSERVAÇÃO | sim | não | Texto livre. |
| N PED ORIGINAL | não | sim | Número do pedido original da compra. |
| CÓD. REVERSO | não | sim | Código da logística reversa (coleta do produto com defeito). Quase nunca preenchido. |
| N PED GARANTIA | não | sim | Número do novo pedido gerado para a troca/garantia. |
| CÓD. RASTREIO | não | sim | Código de rastreio dos Correios do envio da troca. |

## Fluxo de trabalho implícito nas planilhas

1. Cliente reclama (via SAC, site, feira etc.) — registra-se cliente, produto(s), problema e datas.
2. Define-se a **solução** (troca, envio de peça, reembolso, desconto/voucher).
3. Quando há troca: gera-se pedido de garantia (`N PED GARANTIA`), eventualmente logística reversa (`CÓD. REVERSO`), e acompanha-se o envio pelo `CÓD. RASTREIO`.
4. O **status** avança: EM ABERTO → EM PROCESSO → AGUARDANDO RECEBIMENTO → FINALIZADO.

## Problemas do controle atual (o que o sistema deve resolver)

- Sem padronização: datas, telefones, CPFs, SKUs e canais em formato livre; typos ("SGMENTO").
- Metadados enfiados em campos errados (anotações no nome da cliente).
- Cliente duplicado a cada nova linha — não há cadastro único de cliente nem de produto.
- Uma planilha por marca/ano — não há visão consolidada nem histórico unificado.
- STATUS pouco preenchido na KODI; nenhum controle de responsável, prazos ou SLA.
- Nenhum anexo estruturado (fotos do defeito são tratadas fora, vide "(sem foto)").

Esses valores de PROBLEMA, SOLUÇÃO, STATUS, SEGMENTO e LOCAL DA COMPRA devem virar cadastros/enums administráveis no novo sistema, e cada linha deve virar item de uma reclamação vinculada a um cliente único.
