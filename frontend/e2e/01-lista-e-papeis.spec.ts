import { expect, test } from "@playwright/test"

import { apiFullTicket, login } from "./helpers"

test.describe("Lista de tickets e papeis", () => {
  test("admin ve filtros, ordenacao e linha clicavel", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")

    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()
    await expect(page).toHaveURL(/\/tickets$/)

    for (const label of ["Status", "Marca", "Cliente", "Produto", "Pedido", "Prioridade", "Ordenar por"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }
    await expect(page.getByRole("button", { name: "Novo ticket" })).toBeVisible()

    const row = page.getByRole("row").filter({ hasText: `#${ticket.number}` })
    await expect(row).toBeVisible()
    await expect(row).toContainText("Cliente E2E")

    // linha inteira e link real: um clique no meio da linha (fora da coluna do numero) navega
    const alvo = page.getByRole("row").filter({ hasText: `#${ticket.number}` })
    const caixa = await alvo.boundingBox()
    expect(caixa, "linha do ticket sem caixa").toBeTruthy()
    await page.mouse.click(caixa!.x + caixa!.width / 2, caixa!.y + caixa!.height / 2)
    await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}$/)
    await expect(page.getByText(`#${ticket.number}`).first()).toBeVisible()

    await page.goBack()
    // toggle de ordem alterna o rotulo acessivel
    await expect(page.getByRole("button", { name: "Ordem decrescente" })).toBeVisible()
    await page.getByRole("button", { name: "Ordem decrescente" }).click()
    await expect(page.getByRole("button", { name: "Ordem crescente" })).toBeVisible()

    // ordenar por numero crescente: a primeira linha passa a ser o menor numero
    await page.locator("#filtro-ordenar").click()
    await page.getByRole("option", { name: "Numero" }).click()
    await expect(page.getByRole("row").nth(1)).toContainText("#1")
  })

  test("filtro de produto por autocomplete restringe a lista", async ({ page, request }) => {
    const comProduto = await apiFullTicket(request, "admin")
    const semProduto = await apiFullTicket(request, "admin", { items: [] })

    await login(page, request, "admin")
    await page.goto("/tickets")
    await expect(page.getByRole("row").filter({ hasText: `#${semProduto.number}` })).toBeVisible()

    await page.locator("#filtro-produto").fill("Alicate")
    await page.getByRole("button", { name: /Alicate/ }).first().click()

    await expect(page.getByRole("row").filter({ hasText: `#${comProduto.number}` })).toBeVisible()
    await expect(page.getByRole("row").filter({ hasText: `#${semProduto.number}` })).toHaveCount(0)
  })

  test("visualizador nao ve acoes nem campo de comentario", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")

    await login(page, request, "viewer")
    await page.goto("/tickets")
    await expect(page.getByRole("button", { name: "Novo ticket" })).toHaveCount(0)

    await page.goto(`/tickets/${ticket.id}`)
    await expect(page.getByText(`#${ticket.number}`).first()).toBeVisible()
    await expect(page.getByRole("button", { name: "Enviar para analise" })).toHaveCount(0)
    await expect(page.getByPlaceholder("Escreva um comentario interno...")).toHaveCount(0)
    await expect(page.getByText("Somente leitura.")).toBeVisible()
  })

  test("atendente so ve os proprios tickets", async ({ page, request }) => {
    const doAdmin = await apiFullTicket(request, "admin")
    const doAtendente = await apiFullTicket(request, "atendente")

    await login(page, request, "atendente")
    await page.goto("/tickets")
    await expect(page.getByRole("row").filter({ hasText: `#${doAtendente.number}` })).toBeVisible()
    await expect(page.getByRole("row").filter({ hasText: `#${doAdmin.number}` })).toHaveCount(0)

    await page.goto(`/tickets/${doAdmin.id}`)
    await expect(page.getByText("Ticket nao encontrado.")).toBeVisible()
  })
})
