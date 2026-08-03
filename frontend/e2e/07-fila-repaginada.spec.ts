import { expect, test } from "@playwright/test"

import { apiFullTicket, login, ticketCard } from "./helpers"

test.describe("Fila de tickets repaginada", () => {
  test("busca por numero e chips filtram a fila", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()

    const card = ticketCard(page, ticket.number)
    await expect(card).toBeVisible()

    await page
      .getByPlaceholder("Buscar por no, cliente, produto ou pedido")
      .fill(String(ticket.number))
    // a busca e debounced em 400ms: espera a URL refletir o termo antes de
    // olhar a lista, em vez de assertar o resultado na hora
    await expect(page).toHaveURL(new RegExp(`q=${ticket.number}`))
    await expect(card).toBeVisible()

    // chip "Atrasados" e outro recorte (overdue=1); o ticket recem-criado nao
    // e atrasado, entao so a URL e conferida aqui — a lista sob esse recorte
    // nao inclui o card
    await page.getByRole("button", { name: /Atrasados/ }).click()
    await expect(page).toHaveURL(/overdue=1/)
    await expect(card).toHaveCount(0)

    await page.getByRole("button", { name: /^Todos/ }).click()
    await expect(card).toBeVisible()
    await card.click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })

  test("contadores aparecem no subtitulo e nos chips", async ({ page, request }) => {
    await apiFullTicket(request, "admin")
    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()
    await expect(page.getByText(/tickets ativos/)).toBeVisible()
    await expect(page.getByRole("button", { name: /Nao lidos/ })).toBeVisible()
  })

  test("chip Meus tickets filtra por atendente", async ({ page, request }) => {
    const meu = await apiFullTicket(request, "admin")
    const doAtendente = await apiFullTicket(request, "atendente")

    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()

    const chipMeus = page.getByRole("button", { name: /Meus tickets/ })
    await chipMeus.click()
    await expect(chipMeus).toHaveAttribute("aria-pressed", "true")
    await expect(ticketCard(page, meu.number)).toBeVisible()
    await expect(ticketCard(page, doAtendente.number)).toHaveCount(0)
  })

  // Chip "Nao lidos" precisa de fato restringir a fila, nao so mudar a URL:
  // um ticket criado pelo proprio admin fica lido para ele (o backend marca
  // o criador como leitor na hora da criacao — ver
  // 04-comentarios-e-naolido.spec.ts), enquanto um ticket criado por outro
  // usuario fica nao lido ate o admin abrir o detalhe. O recorte precisa
  // excluir o primeiro e manter o segundo.
  test("chip Nao lidos filtra a fila por atividade nao lida", async ({ page, request }) => {
    const lido = await apiFullTicket(request, "admin")
    const naoLido = await apiFullTicket(request, "atendente")

    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()
    await expect(ticketCard(page, lido.number)).toBeVisible()
    await expect(ticketCard(page, naoLido.number)).toBeVisible()

    const chipNaoLidos = page.getByRole("button", { name: /Nao lidos/ })
    await chipNaoLidos.click()
    await expect(page).toHaveURL(/unread=1/)
    await expect(chipNaoLidos).toHaveAttribute("aria-pressed", "true")

    await expect(ticketCard(page, lido.number)).toHaveCount(0)
    await expect(ticketCard(page, naoLido.number)).toBeVisible()
  })

  // Um status sem chip equivalente (ex.: "aprovado" — os cards de KPI do
  // dashboard linkam para esses) e um recorte que os selects do header
  // conseguem expressar mas os chips nao representam: nenhum chip fica
  // marcado como ativo, nem "Todos".
  test("nenhum chip fica ativo para um status sem chip equivalente", async ({ page, request }) => {
    await apiFullTicket(request, "admin")
    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()

    await page.getByRole("combobox", { name: "Status" }).click()
    await page.getByRole("option", { name: "Aprovado" }).click()
    await expect(page).toHaveURL(/status=aprovado/)

    for (const nome of [
      /^Todos/,
      /Abertos/,
      /Aguardando analise/,
      /Atrasados/,
      /Nao lidos/,
      /Meus tickets/,
    ]) {
      await expect(page.getByRole("button", { name: nome })).toHaveAttribute(
        "aria-pressed",
        "false",
      )
    }
  })

  // O deep link "Ver historico" filtra a fila por um cliente sem controle
  // proprio no header: a pill abaixo dos chips e o unico indicador desse
  // recorte e o unico jeito de remove-lo.
  test("deep link de cliente mostra a pill e o X remove o recorte", async ({ page, request }) => {
    const doCliente = await apiFullTicket(request, "admin")
    const deOutro = await apiFullTicket(request, "admin")

    await login(page, request, "admin")
    await page.goto(`/tickets/${doCliente.id}`)
    await page.getByRole("link", { name: "Ver historico" }).click()

    await expect(page).toHaveURL(/customer_id=/)
    // ancora no container da pill: os cards tambem renderizam "Cliente E2E",
    // entao um getByText solto casaria a lista mesmo sem nome na pill
    const pill = page.getByText("Filtrando por cliente").locator("..")
    await expect(pill).toBeVisible()
    await expect(pill).toContainText("Cliente E2E")
    await expect(ticketCard(page, doCliente.number)).toBeVisible()
    // cada apiFullTicket cria um cliente novo (CPF aleatorio): o ticket do
    // outro cliente prova que o recorte realmente restringe a fila
    await expect(ticketCard(page, deOutro.number)).toHaveCount(0)

    await page.getByRole("button", { name: "Remover filtro de cliente" }).click()
    await expect(page).not.toHaveURL(/customer_id=/)
    await expect(page.getByText("Filtrando por cliente")).toHaveCount(0)
    await expect(ticketCard(page, deOutro.number)).toBeVisible()
  })
})
