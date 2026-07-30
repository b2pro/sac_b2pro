import { expect, test } from "@playwright/test"

import { apiFullTicket, apiUploadAttachment, login } from "./helpers"

test.describe("Visibilidade: dashboard, relatorios e midias", () => {
  test("dashboard mostra KPIs e card clicavel pre-filtra a lista", async ({ page, request }) => {
    await apiFullTicket(request, "admin")
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Dashboard" }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByText("Total", { exact: true })).toBeVisible()
    await expect(page.getByText("Tempo medio de resolucao")).toBeVisible()
    await expect(page.getByText("Distribuicao por status")).toBeVisible()

    await page.getByRole("link", { name: /Abertos/ }).click()
    await expect(page).toHaveURL(/\/tickets\?.*status=aberto/)
  })

  test("relatorio exige filtro, lista com link e exporta CSV", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Relatorios" }).click()
    await expect(page).toHaveURL(/\/relatorios$/)
    // estado inicial: nada consultado ate filtrar
    await expect(page.getByText("Nenhum filtro aplicado")).toBeVisible()

    await page.getByLabel("Periodo — de").fill("2026-01-01")
    await page.getByRole("button", { name: "Filtrar" }).click()
    const row = page.locator("table tbody tr").filter({ hasText: `#${ticket.number}` })
    await expect(row).toBeVisible()

    const download = page.waitForEvent("download")
    await page.getByRole("button", { name: "Exportar CSV" }).click()
    expect((await download).suggestedFilename()).toBe("relatorio-tickets.csv")

    // a linha e clicavel (TicketRow navega no clique) e leva ao detalhe do
    // ticket certo — nao so aparece na tabela, funciona como link de verdade
    await row.click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })

  test("galeria mostra anexo e lightbox leva ao ticket", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await apiUploadAttachment(request, "admin", ticket.id, "e2e/fixtures/defeito.png")
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Midias" }).click()
    await expect(page).toHaveURL(/\/midias$/)

    // aria-label do MediaTile carrega o filename e o numero do ticket: como
    // varios specs sobem "defeito.png" para tickets diferentes, o numero do
    // ticket e o unico jeito seguro de mirar exatamente o tile deste teste.
    const tile = page.getByRole("button", {
      name: new RegExp(`Abrir anexo defeito\\.png do ticket #${ticket.number}$`),
    })
    await expect(tile).toBeVisible()
    await tile.click()

    await page.getByRole("link", { name: new RegExp(`Ver ticket #${ticket.number}`) }).click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })
})
