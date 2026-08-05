# Identidade visual — SAC-B2PRO

Direcao artistica definida pelo produto (2026-07-27). Vale para todo o frontend; qualquer trabalho de UI deve seguir este documento. Pensado para um sistema operacional de suporte: atendentes usando 8h por dia, nao um marketing site.

## Sensacao geral

Algo entre um painel de controle industrial e uma prancheta de oficina — serio, funcional. O laranja aparece somente como sinalizacao (SLA, prioridade, acao primaria), nunca como decoracao. O Floral White nao e "fundo bonito generico": funciona quase como papel, com contraste suficiente para nao ficar clinico feito hospital.

## Paleta e hierarquia de cor

| Cor | Hex | Uso |
|---|---|---|
| Floral White | `#fffcf2` | Fundo base das telas e cards. Nunca branco puro. |
| Silver | `#ccc5b9` | Bordas, divisores, estados neutros (badge "aguardando", texto secundario). E o "cinza" da paleta, puxado pro bege — evita o cinza-azulado padrao de shadcn. |
| Charcoal Brown | `#403d39` | Corpo de texto principal. Nunca preto puro; ar de documento impresso. |
| Carbon Black | `#252422` | Titulos, texto de alta enfase e fundo do sidebar/nav (navegacao escura contra conteudo claro: separa "onde eu navego" de "onde eu trabalho"). |
| Spicy Paprika | `#eb5e28` | So tres usos: acao primaria (ex.: "Aprovar", "Enviar a analise"), indicador de urgencia/SLA vencendo e numero do ticket em destaque. Se aparecer em mais de 3 lugares na mesma tela, esta errado. Como PREENCHIMENTO, borda e sinalizacao e este valor exato; como TEXTO ele reprova AA nos dois temas (3,32:1 no claro, 4,09:1 no escuro), entao texto em Paprika usa `--primary-text` — mesmo matiz e saturacao, luminosidade ajustada por tema. Rotulo EM CIMA do Paprika (botao primario, contador) e Carbon Black, nao Floral White: 4,55:1 contra 3,32:1. |
| Paprika para texto | `#b13d11` claro, `#f18a5f` escuro | O valor de `--primary-text`, o irmao do Paprika que carrega TEXTO (link, rotulo, numero de ticket). Matiz e saturacao presos ao Paprika (17/83); so a luminosidade muda, entao e a mesma cor e nao um segundo laranja na marca. APROVADO em 2026-08-05 apos comparar tres candidatos. |

**A superficie que decide o contraste do `--primary-text` e a LINHA EM HOVER**, nao o fundo
da pagina: no hover o preenchimento sobe (`#ece7da` no claro, `#3c3935` no escuro) e o
contraste cai para o pior caso da paleta — 4,80:1 e 4,67:1 com os valores aprovados. Ao
mexer em qualquer tom aqui, e esse numero que precisa passar de 4,5:1, nunca o do fundo.

O tom mais proximo do Paprika que ainda passaria e `#b64011` / `#f0865c`, e ele foi
RECUSADO de proposito: deixa so 0,06 e 0,02 de folga acima do piso. A rampa escura e
conhecidamente comprimida (fundo -> card 1,11, card -> muted 1,14) e descomprimi-la
significa clarear as superficies escuras, o que consumiria essa folga e derrubaria o tom
abaixo de AA. Os valores aprovados ficam um passo de luminosidade atras do limite
justamente para sobreviver a essa revisao.

## Tipografia

- Dois pesos de UMA familia so para o corpo — sans humanista e discreta: Inter, Public Sans ou IBM Plex Sans. Nada de par de fontes editorial; o sistema precisa de legibilidade em tabela densa.
- Monoespacada (JetBrains Mono ou IBM Plex Mono) SOMENTE para: numeros de ticket, codigos de rastreio, CPF/CNPJ e timestamps. Comunica "dado tecnico" vs "texto humano" sem icone e reforca a leitura tabular do sistema.

## Bordas, profundidade e espacamento

- Raio pequeno e consistente: a escala do sistema esta travada em 4px / 5px / 6px (`rounded-sm` / `rounded-md` / `rounded-lg`), e nenhum componente usa valor fora dela. Nunca grande (app de consumo). Duas excecoes, porque nao sao raio de card/controle: circulo e pilula (`rounded-full`), que sao a forma do elemento; e linha full-bleed dentro de um container que ja tem o raio, que fica em zero por nao ter canto visivel. O raio e utilitario, nao estetico.
- Bordas de 1px em Silver em repouso; no focus/hover a borda vira Charcoal Brown. Nunca sombra colorida ou glow.
- Zero drop-shadow em elemento no fluxo. Se precisar de profundidade ali: borda + degrade de no maximo 2% de opacidade (quase invisivel). Camada flutuante que cobre conteudo (popover, menu, select, dropdown de autocomplete) pode ter uma sombra discreta — ela e o unico sinal de sobreposicao, ja que popover e card sao a mesma superficie. E nunca vem sozinha: sempre acompanhada de borda, porque no tema escuro a sombra quase nao aparece. Dialog dispensa a sombra: o escurecedor atras dele ja faz a separacao. Nunca gradiente visivel.
- Espacamento em escala de 4px: respiro generoso vertical entre secoes (24-32px), compacto horizontal dentro de linhas de tabela (8-12px). Densidade de linha importa mais que espaco em branco bonito.
- Cards de ticket: borda esquerda de 3px solida na cor do status (nao badge colorido solto). Detalhe estrutural e funcional — da pra escanear a fila pela lateral sem ler texto.

## Elemento-assinatura: trilha de status

A maquina de estados do ticket vira a peca visual central: uma trilha de status horizontal fina — NAO um stepper generico com bolinhas numeradas e check verde. Barra segmentada onde cada segmento e preenchido em Charcoal Brown ate o estado atual; o segmento ativo pulsa suavemente em Paprika apenas quando o SLA esta apertado. Comunica de imediato "onde esse ticket esta e ele esta em risco?".

## O que evitar

- Nenhum gradiente, nem sutil, em botao ou header.
- Nenhum icone estilo "outline arredondado fofo". Lucide/Feather funciona, com peso de traco fino e consistente — nunca misturar estilos de icone.
- Sidebar escura sem glow e sem indicador ativo neon: indicador ativo em Paprika solido de 2px, sem blur.
- Nenhum empty state com ilustracao fofa: texto direto ("Nenhum ticket aberto para este filtro").
- Nenhum emoji

## Ícones

- Biblioteca: `lucide-react` — já é a base usada pelos componentes shadcn/ui, não usar nenhuma outra lib de ícones no projeto.
- `strokeWidth` fixo em `1.5` em todos os ícones do sistema, sem exceção. Se um componente shadcn vier com outro valor, sobrescrever para manter consistência.
- Tamanho padrão: `16px` em contextos de tabela/lista (badges, ações inline) e `20px` em botões e headers. Não usar tamanhos intermediários.
- Nunca usar ícones preenchidos (`fill`) — sempre outline, mesmo em estados ativos/selecionados (usar cor, não preenchimento, para indicar estado).
- Cor padrão herda do texto ao redor (`currentColor`); só usar a cor de acento (Paprika) em ícones de ação primária, alerta de SLA ou status crítico — nunca como decoração.
- Se não existir um ícone específico de domínio (ex: logística reversa, garantia) na lib, compor com 2 ícones simples do Lucide em vez de importar outra biblioteca com estilo diferente.