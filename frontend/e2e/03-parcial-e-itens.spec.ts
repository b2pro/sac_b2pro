import { expect, test } from "@playwright/test"

import { apiFullTicket, formatCpf, login, randomCpf, selectOption } from "./helpers"

test("ticket parcial e completado pelo detalhe e segue para analise", async ({ page, request }) => {
  // um cliente ja existente no tenant, para exercitar o vinculo por documento
  const cpf = randomCpf()
  await apiFullTicket(request, "admin", {
    customer: { name: "Marcos Vinculo", document: cpf },
  })

  await login(page, request, "admin")
  await page.goto("/tickets/novo")

  // --- criacao parcial: apenas marca e prioridade ---
  await selectOption(page, "marca", "STALEKS")
  await selectOption(page, "prioridade", /Baixa/)
  await expect(
    page.getByText("Voce pode salvar parcialmente e completar depois", { exact: false }),
  ).toBeVisible()
  await page.getByRole("button", { name: "Criar ticket" }).click()
  await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}$/, { timeout: 20_000 })
  await expect(page.getByText("Aberto").first()).toBeVisible()
  await expect(page.getByText("Nenhum cliente vinculado.")).toBeVisible()
  await expect(page.getByText("Nenhum item registrado.")).toBeVisible()

  // --- enviar para analise falha por incompletude ---
  await page.getByRole("button", { name: "Enviar para analise" }).click()
  await expect(page.getByText(/incompleto/i).first()).toBeVisible()
  await expect(page.getByText("Aberto").first()).toBeVisible()

  // --- adicionar item pelo card Itens ---
  await page.getByRole("button", { name: "Adicionar item" }).click()
  await page.locator("#item-produto").fill("Tesoura")
  await page.getByRole("button", { name: /Tesoura/ }).first().click()
  await selectOption(page, "item-defeito", /.+/)
  await page.locator("#item-quantidade").fill("3")
  await page.getByRole("dialog").getByRole("button", { name: "Adicionar" }).click()
  await expect(page.getByRole("cell", { name: "Tesoura Reta STALEKS", exact: true })).toBeVisible()
  await expect(page.getByRole("cell", { name: "3", exact: true })).toBeVisible()

  // --- vincular cliente e preencher descricao pelo dialog Editar dados ---
  await page.getByRole("button", { name: "Mais acoes do ticket" }).click()
  await page.getByRole("menuitem", { name: "Editar dados" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("Editar dados do ticket")
  await dialog.locator("#editar-documento").fill(formatCpf(cpf))
  await expect(dialog.getByText("Cliente vinculado: Marcos Vinculo")).toBeVisible()
  await dialog.locator("#editar-descricao").fill("Cliente relatou oxidacao na lamina.")
  await dialog.getByRole("button", { name: "Salvar" }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText("Marcos Vinculo", { exact: true })).toBeVisible()

  // --- agora o envio para analise passa ---
  await page.getByRole("button", { name: "Enviar para analise" }).click()
  await expect(page.getByText("Aguardando analise").first()).toBeVisible()
})

test("itens ficam somente leitura fora de estado editavel", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")

  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByRole("button", { name: "Adicionar item" })).toBeVisible()

  // aprovado: card de itens perde as acoes de edicao
  await page.getByRole("button", { name: "Enviar para analise" }).click()
  await expect(page.getByText("Aguardando analise").first()).toBeVisible()
  await page.getByRole("button", { name: "Aprovar", exact: true }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Confirmar" }).click()
  await expect(page.getByText("Aprovado").first()).toBeVisible()
  await expect(page.getByRole("button", { name: "Adicionar item" })).toHaveCount(0)
})
