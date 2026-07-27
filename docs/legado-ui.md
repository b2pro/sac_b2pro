# Legado SAC-Tickets — UI/UX (referência para o novo front)

Levantamento do front do projeto `../SAC-Tickets` (Laravel 12 + Blade + Alpine.js + Tailwind via CDN, 59 views). O novo front React+TS+Vite deve se inspirar na disposição das telas e melhorar tudo listado em "Pontos fracos".

## Layout geral

- **Sidebar fixa à esquerda** (288px, fundo branco, borda direita) com a marca no topo (eyebrow + "SAC Tickets" + nome do tenant) e navegação em pílulas; item ativo em fundo escuro.
- **Header** no topo do conteúdo: eyebrow "Painel operacional" + título da página à esquerda; sino de notificações (dropdown com polling de 20s, badge de contagem, som e Notification API) e card do usuário (nome, tenant e papel, botão "Sair") à direita.
- Conteúdo em `max-w-7xl` centralizado, fundo cinza-claro, flash messages em banners no topo. Sem rodapé, sem busca global, sem menu mobile.
- Lightbox global para imagens/vídeos.

### Menu de navegação (ordem)

Grupo **Tickets**: Dashboard, Tickets, Relatórios, Mídias, Cadastros (accordion: Produtos, Defeitos, Soluções, Clientes, Usuários — este último só admin).
Grupo **Eventos** (módulo opcional): Análise, Formulários.
Sidebar do super-admin (layout separado): Dashboard Geral, Organizações, Super Admins.
Menus condicionados por módulo do tenant e por papel do usuário.

## Telas

### Dashboard
- 7 KPI cards clicáveis (levam à lista de tickets pré-filtrada): Total, Abertos, Aguardando análise, Atrasados (SLA), Aprovados no mês, Declinados no mês, Finalizados no mês.
- Abaixo, 2 colunas (2/3 + 1/3): tabela "Tickets recentes" + coluna com "Distribuição por status" (lista com badges e contagens) e "Tempo médio de resolução".
- Sem nenhum gráfico (nenhuma lib de charts no projeto).

### Lista de tickets
- Card de filtros no topo (Status, Cliente por nome/CPF/CNPJ, Produto, Pedido, Prioridade) com botões Filtrar/Limpar.
- Card com tabela de 10 colunas (#Ticket, Cliente, Produto, Defeito, Prioridade, Status, SLA, Atendente, Abertura, Ações), colunas somem por breakpoint. Botão "Novo ticket" no header do card.
- Linha inteira clicável (via onclick), indicador de "não lida" (fundo esmeralda + bolinha + chip "nova"), menu "kebab" por linha (Marcar como não lida, Editar, Excluir), paginação padrão Laravel.

### Detalhe do ticket (tela mais importante, 563 linhas, sem abas)
- **Hero card**: número do ticket + badges de status/prioridade/SLA + metadados; botões Editar / Novo ticket / Excluir.
- **Coluna esquerda (2/3)**: 4 cards de dados (Informações gerais; Dados do cliente com botão "Ver histórico"; Dados da compra; Produtos & defeitos), seção de **Anexos** (upload inline, grid de cards com thumb, rename inline, lightbox) e **Comentários internos** em formato chat (bolhas, reply com citação clicável, Enter envia, polling 7s, envio com reload de página).
- **Coluna direita (1/3)**: "Ações do ticket" — pilha de mini-formulários, um por transição de estado (Reabrir, Enviar para análise, Aprovar, Declinar, Concluir com solução obrigatória, Cancelar, Código reverso, Produto recebido, Pedido de garantia), cada um com botão de cor diferente; "Códigos reversos" registrados; "Timeline" de eventos (sem linha conectora).

### Criação de ticket (página única, sem wizard)
1. **Dados do cliente**: CPF/CNPJ com máscara e lookup automático (sugestão inline que preenche tudo e vincula `customer_id`), CEP com autofill via ViaCEP, endereço completo.
2. **Dados da compra**: local da compra com autocomplete (debounce + navegação por teclado), pedido, datas de compra/entrega.
3. **Detalhes do caso**: produtos repetíveis (produto + defeito por linha), atendente (default usuário logado), supervisor, prioridade (define SLA), descrição, anexos (até 10 arquivos de 50 MB).

### Demais telas
- **Relatórios**: 8 filtros, 4 KPI cards, tabela de resultados (sem paginação/links) + rankings de Top produtos/defeitos/soluções; botão Exportar CSV.
- **Mídias**: galeria em grid com filtros, thumbs clicáveis para lightbox.
- **Cadastros (5 CRUDs idênticos)**: card com tabela + botão "Novo", ações Editar/Excluir por linha, formulários em card único com grid; clientes têm busca e botão "Histórico".
- **Histórico do cliente**: identificação + tabela dos tickets dele.
- **Preferências de notificação**: checkboxes em cards (popup do sistema, som), teste de notificação.
- **Login**: fundo escuro com gradiente, card branco central, email + senha + "manter sessão".
- **Módulo Eventos**: lista de formulários em cards com link público copiável; tela de análise com chips de filtro rápido e lixeira; construtor de formulários drag-and-drop com prévia ao vivo e lógica condicional; formulário público white-label com cores do tenant.

## Vocabulário visual (o que preservar, tokenizado)

- Neutros slate; primário de ação = quase-preto; cores semânticas: verde sucesso/aprovado, rosa/vermelho erro/destrutivo, âmbar aviso, laranja aguardando, roxo em análise, teal recebido, indigo reverso, sky acento.
- Cards brancos com borda e sombra leve, header de card com título+subtítulo+ação; badges pill com ring (status, prioridade com dot, SLA com prazo relativo); empty states com borda tracejada.
- Padrões de UX que funcionam bem e devem ser mantidos: KPI cards que filtram a lista, lookup de cliente por documento, autocomplete de local de compra, indicador de não-lido por linha, chat com reply, estrutura 2/3+1/3 no detalhe do ticket.

## Pontos fracos a corrigir no redesign

1. Tailwind e Alpine via CDN em produção (build Vite existe mas não é usado); JS inline duplicado entre views.
2. Ícones são emojis literais — trocar por icon set (Lucide).
3. Sem menu mobile (sidebar some abaixo de 1024px sem alternativa).
4. Coluna de ações do ticket = pilha de 6-8 formulários com cores diferentes e sem hierarquia — virar 1 ação primária contextual + menu de ações secundárias com modal/drawer.
5. Sem modais nem toasts: `window.confirm()`/`alert()` nativos e flash banners no topo.
6. Linhas de tabela clicáveis por onclick (sem link real), kebab com posicionamento manual frágil.
7. Tabelas sem ordenação, sem seleção múltipla, sem ações em lote, sem chips de filtros ativos.
8. Dashboard e relatórios sem gráficos; relatórios sem paginação nem links para os tickets.
9. Dados duplicados no detalhe do ticket; timeline sem linha conectora; "Novo ticket" como CTA fora de contexto no detalhe.
10. Header sem busca global, sem menu de perfil; "Sair" permanentemente exposto.
11. Acessibilidade fraca (sem focus-visible, aria, contraste limítrofe); sem loading states, skeletons ou progresso de upload; uploads sem drag-and-drop/preview.
12. ViaCEP chamado direto do browser sem tratamento de erro; sem dark mode; sem design tokens; raios de borda exagerados (ar "bubbly").
