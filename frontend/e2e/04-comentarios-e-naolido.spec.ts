import { expect, test } from "@playwright/test"

import { apiFullTicket, login, ticketCard } from "./helpers"

test("comentario com resposta e ciclo de nao lido entre usuarios", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")

  // --- supervisor comenta no ticket do admin ---
  await login(page, request, "supervisor")
  await page.goto(`/tickets/${ticket.id}`)
  const composer = page.getByPlaceholder("Escreva um comentario interno...")
  await composer.fill("Preciso da nota fiscal para seguir com a analise.")
  await page.getByRole("button", { name: "Enviar", exact: true }).click()
  await expect(page.getByText("Preciso da nota fiscal para seguir com a analise.")).toBeVisible()

  // --- admin ve o ticket como nao lido na lista ---
  // TicketQueueCard marca "nao lido" com um ponto decorativo (role="img",
  // aria-label "Atividade nao lida"), sem texto visivel — o equivalente da
  // antiga celula "Nao lido" da tabela.
  await login(page, request, "admin")
  await page.goto("/tickets")
  await expect(
    ticketCard(page, ticket.number).getByRole("img", { name: "Atividade nao lida" }),
  ).toBeVisible()

  // --- abrir o detalhe marca como lido ---
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Preciso da nota fiscal para seguir com a analise.")).toBeVisible()
  await page.goto("/tickets")
  await expect(
    ticketCard(page, ticket.number).getByRole("img", { name: "Atividade nao lida" }),
  ).toHaveCount(0)

  // --- responder citando o comentario do supervisor ---
  await page.goto(`/tickets/${ticket.id}`)
  await page.getByRole("button", { name: "Responder" }).first().click()
  await page.getByPlaceholder("Escreva um comentario interno...").fill("Nota fiscal anexada no pedido.")
  await page.getByRole("button", { name: "Enviar", exact: true }).click()
  await expect(page.getByText("Nota fiscal anexada no pedido.")).toBeVisible()
  await expect(page.getByText("Dora Supervisora").first()).toBeVisible()

  // --- marcar como nao lido de novo pelo menu ---
  await page.getByRole("button", { name: "Mais acoes do ticket" }).click()
  await page.getByRole("menuitem", { name: "Marcar como nao lido" }).click()
  await page.goto("/tickets")
  await expect(
    ticketCard(page, ticket.number).getByRole("img", { name: "Atividade nao lida" }),
  ).toBeVisible()
})

test("declinar exige motivo e encerra o ticket", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")

  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)
  await page.getByRole("button", { name: "Enviar para analise" }).click()
  await expect(page.getByText("Aguardando analise").first()).toBeVisible()

  await page.getByRole("button", { name: "Declinar" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("Declinar ticket")

  // motivo em branco: o dialog nao envia e avisa
  await dialog.getByRole("button", { name: "Declinar" }).click()
  await expect(page.getByText(/motivo/i).first()).toBeVisible()
  await expect(dialog).toBeVisible()

  await dialog.getByRole("textbox").fill("Fora do prazo de garantia.")
  await dialog.getByRole("button", { name: "Declinar" }).click()
  await expect(page.getByText("Declinado").first()).toBeVisible()
  await expect(page.getByText("Fora do prazo de garantia.").first()).toBeVisible()

  // encerrado: reabrir volta para aberto (nunca houve aprovacao)
  await page.getByRole("button", { name: "Reabrir" }).click()
  await expect(page.getByText("Aberto").first()).toBeVisible()
})
