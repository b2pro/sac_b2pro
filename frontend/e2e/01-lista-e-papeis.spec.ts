import { expect, test } from "@playwright/test"

import { apiFullTicket, login, ticketCard } from "./helpers"

test.describe("Lista de tickets e papeis", () => {
  test("admin ve filtros, ordenacao e card clicavel", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")

    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()
    await expect(page).toHaveURL(/\/tickets$/)

    // A fila repaginada trocou o card de filtros por controles no header:
    // busca livre e os selects de Status / Marca / Atendente / Ordenar por.
    // Os campos antigos de Cliente, Produto e Pedido nao tem mais controle
    // proprio — a busca livre cobre os tres (ver teste abaixo) — e o filtro
    // de Prioridade foi removido da tela sem substituto.
    await expect(
      page.getByPlaceholder("Buscar por nº, cliente, produto ou pedido"),
    ).toBeVisible()
    for (const label of ["Status", "Marca", "Atendente", "Ordenar por"]) {
      await expect(page.getByRole("combobox", { name: label })).toBeVisible()
    }
    // "Novo ticket" e um Button asChild em cima de um Link: o papel
    // acessivel real e "link", nao "button"
    await expect(page.getByRole("link", { name: "Novo ticket" })).toBeVisible()

    const card = ticketCard(page, ticket.number)
    await expect(card).toBeVisible()
    await expect(card).toContainText("Cliente E2E")

    // o card inteiro e um <a> (TicketQueueCard): um clique no canto oposto ao
    // numero, longe de qualquer badge, ainda navega
    const caixa = await card.boundingBox()
    expect(caixa, "card do ticket sem caixa").toBeTruthy()
    await page.mouse.click(caixa!.x + caixa!.width - 15, caixa!.y + caixa!.height - 8)
    await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}$/)
    await expect(page.getByText(`#${ticket.number}`).first()).toBeVisible()

    await page.goBack()
    // toggle de ordem alterna o rotulo acessivel
    await expect(page.getByRole("button", { name: "Ordem decrescente" })).toBeVisible()
    await page.getByRole("button", { name: "Ordem decrescente" }).click()
    await expect(page.getByRole("button", { name: "Ordem crescente" })).toBeVisible()

    // ordenar por numero crescente: o primeiro card passa a ser o menor numero
    await page.getByRole("combobox", { name: "Ordenar por" }).click()
    await page.getByRole("option", { name: "Número" }).click()
    const cards = page.getByRole("link").filter({ hasText: /^#\d+/ })
    await expect(cards.first()).toContainText("#1")
  })

  // Substitui o antigo "filtro de produto por autocomplete restringe a
  // lista": o campo `#filtro-produto` (autocomplete que selecionava um
  // product_id exato) nao existe mais na fila repaginada. A capacidade de
  // restringir a fila por produto continua, agora pela busca livre do
  // header (placeholder "Buscar por nº, cliente, produto ou pedido"), que e
  // o mecanismo que a UI nova oferece para isso.
  test("busca livre por produto restringe a fila", async ({ page, request }) => {
    const comProduto = await apiFullTicket(request, "admin")
    const semProduto = await apiFullTicket(request, "admin", { items: [] })

    await login(page, request, "admin")
    await page.goto("/tickets")
    await expect(ticketCard(page, semProduto.number)).toBeVisible()

    await page.getByPlaceholder("Buscar por nº, cliente, produto ou pedido").fill("Alicate")
    // busca e debounced (400ms): esperar a URL refletir o termo antes de
    // conferir a lista, em vez de checar o resultado na hora
    await expect(page).toHaveURL(/q=Alicate/)

    await expect(ticketCard(page, comProduto.number)).toBeVisible()
    await expect(ticketCard(page, semProduto.number)).toHaveCount(0)
  })

  test("visualizador nao ve acoes nem campo de comentario", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")

    await login(page, request, "viewer")
    await page.goto("/tickets")
    await expect(page.getByRole("link", { name: "Novo ticket" })).toHaveCount(0)

    await page.goto(`/tickets/${ticket.id}`)
    await expect(page.getByText(`#${ticket.number}`).first()).toBeVisible()
    await expect(page.getByRole("button", { name: "Enviar para análise" })).toHaveCount(0)
    await expect(page.getByPlaceholder("Escreva um comentário interno...")).toHaveCount(0)
    await expect(page.getByText("Somente leitura.")).toBeVisible()
  })

  test("atendente so ve os proprios tickets", async ({ page, request }) => {
    const doAdmin = await apiFullTicket(request, "admin")
    const doAtendente = await apiFullTicket(request, "atendente")

    await login(page, request, "atendente")
    await page.goto("/tickets")
    await expect(ticketCard(page, doAtendente.number)).toBeVisible()
    await expect(ticketCard(page, doAdmin.number)).toHaveCount(0)

    await page.goto(`/tickets/${doAdmin.id}`)
    await expect(page.getByText("Ticket não encontrado.")).toBeVisible()
  })
})
