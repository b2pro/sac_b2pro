import { expect, test } from "@playwright/test"

import { formatCpf, loginViaForm, randomCpf, selectOption } from "./helpers"

test("criacao completa pela UI e fluxo ate finalizado", async ({ page }) => {
  const cpf = randomCpf()

  await loginViaForm(page, "admin")
  await page.goto("/tickets")
  await page.getByRole("button", { name: "Novo ticket" }).click()
  await expect(page).toHaveURL(/\/tickets\/novo$/)

  // --- Cliente novo (documento inexistente) ---
  await page.locator("#documento").fill(formatCpf(cpf))
  await expect(page.getByText("Cliente ja cadastrado", { exact: false })).toHaveCount(0)
  await page.locator("#cliente-nome").fill("Joana Prado")
  await page.locator("#cliente-telefone").fill("11987654321")
  await page.locator("#cliente-email").fill("joana.prado@example.com")

  // CEP: autofill quando o ViaCEP responde; se falhar, preenchimento manual
  await page.locator("#cliente-cep").fill("01001-000")
  const cidade = page.locator("#cliente-cidade")
  await expect(async () => {
    const preenchida = await cidade.inputValue()
    expect(preenchida.length).toBeGreaterThan(0)
  })
    .toPass({ timeout: 8000 })
    .catch(async () => {
      await cidade.fill("Sao Paulo")
      await page.locator("#cliente-uf").fill("SP")
    })
  await page.locator("#cliente-numero").fill("100")

  // --- Compra: canal por autocomplete ---
  await page.locator("#canal").fill("SAC")
  await page.getByRole("button", { name: "SAC", exact: true }).click()
  await page.locator("#pedido").fill("PED-E2E-001")
  await page.locator("#data-compra").fill("2026-07-01")
  await page.locator("#data-entrega").fill("2026-07-05")

  // --- Caso ---
  await selectOption(page, "marca", "KODI")
  await selectOption(page, "prioridade", /Urgente/)
  await page.locator("#descricao").fill("Alicate chegou com a ponta torta e sem corte.")

  await page.getByRole("button", { name: "Adicionar item" }).click()
  await page.getByPlaceholder("Buscar produto por nome ou SKU").fill("Alicate")
  await page.getByRole("button", { name: /Alicate/ }).first().click()
  await page.getByRole("combobox").filter({ hasText: "Defeito" }).click()
  await page.getByRole("option").first().click()

  await page.getByRole("button", { name: "Criar ticket" }).click()

  // --- Detalhe do ticket criado ---
  await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}$/, { timeout: 20_000 })
  await expect(page.getByText("Aberto").first()).toBeVisible()
  await expect(page.getByText("Joana Prado")).toBeVisible()
  await expect(page.getByText(formatCpf(cpf))).toBeVisible()
  await expect(page.getByText("PED-E2E-001")).toBeVisible()
  // O placeholder "Anexos chegam na Fase 2B" foi substituido pelo card real de
  // anexos (Task 12); sem upload neste fluxo, o card mostra o estado vazio.
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()

  // --- Fluxo: aberto -> aguardando_analise ---
  await page.getByRole("button", { name: "Enviar para analise" }).click()
  await expect(page.getByText("Aguardando analise").first()).toBeVisible()

  // --- aguardando_analise -> aprovado (dialog com notas) ---
  await expect(page.getByRole("button", { name: "Declinar" })).toBeVisible()
  await page.getByRole("button", { name: "Aprovar", exact: true }).click()
  await expect(page.getByRole("dialog")).toContainText("Aprovar ticket")
  await page.getByRole("dialog").getByRole("button", { name: "Confirmar" }).click()
  await expect(page.getByText("Aprovado").first()).toBeVisible()

  // --- aprovado -> aguardando_envio_reverso (registrar reverso) ---
  await page.getByRole("button", { name: "Registrar reverso" }).click()
  await expect(page.getByRole("dialog")).toContainText("Registrar reverso")
  await page.getByRole("dialog").getByRole("textbox").fill("BR123456789E2E")
  await page.getByRole("dialog").getByRole("button", { name: "Registrar" }).click()
  await expect(page.getByText("Aguardando envio reverso").first()).toBeVisible()
  await expect(page.getByText("BR123456789E2E").first()).toBeVisible()

  // --- aguardando_envio_reverso -> produto_recebido ---
  await page.getByRole("button", { name: "Produto recebido" }).click()
  await expect(page.getByText("Produto recebido").first()).toBeVisible()

  // --- produto_recebido -> finalizado (solucao obrigatoria) ---
  await page.getByRole("button", { name: "Finalizar", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog).toContainText("Finalizar ticket")
  await dialog.getByRole("combobox").click()
  await page.getByRole("option").first().click()
  await dialog.getByRole("button", { name: "Finalizar" }).click()
  await expect(page.getByText("Finalizado").first()).toBeVisible()

  // encerrado: chat vira somente leitura e a timeline registrou as transicoes
  await expect(page.getByPlaceholder("Escreva um comentario interno...")).toHaveCount(0)
  await expect(page.getByText("Ticket encerrado", { exact: false })).toBeVisible()
  const conteudo = page.locator("main")
  await expect(conteudo.getByText("Ticket finalizado")).toBeVisible()
  await expect(conteudo.getByText("Codigo reverso registrado")).toBeVisible()
  await expect(conteudo.getByText("Ticket aprovado")).toBeVisible()
  await expect(conteudo.getByText("Ticket criado")).toBeVisible()
})
