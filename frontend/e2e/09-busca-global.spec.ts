import { expect, test } from "@playwright/test"

import { apiFullTicket, formatCpf, login, randomCpf } from "./helpers"

test.describe("Busca global (Ctrl+K)", () => {
  test("Ctrl+K abre a palette e busca por documento acha o cliente", async ({ page, request }) => {
    const documento = randomCpf()
    await apiFullTicket(request, "admin", {
      customer: { name: "Cliente Busca Global", document: documento },
    })

    await login(page, request, "admin")
    await expect(page.getByRole("combobox", { name: "Termo de busca" })).toHaveCount(0)

    await page.keyboard.press("Control+k")
    const campo = page.getByRole("combobox", { name: "Termo de busca" })
    await expect(campo).toBeVisible()

    // documento formatado, como quem digita a partir de um documento em maos --
    // exercita a normalizacao para digitos que o backend faz antes de comparar.
    await campo.fill(formatCpf(documento))
    const opcao = page.getByRole("option", { name: /Cliente Busca Global/ })
    await expect(opcao).toBeVisible()
    await expect(opcao).toContainText(formatCpf(documento))

    await opcao.click()
    await expect(page).toHaveURL(/\/cadastros\/clientes$/)
  })

  test("busca por numero de ticket navega direto ao detalhe", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await login(page, request, "admin")

    await page.keyboard.press("Control+k")
    await page.getByRole("combobox", { name: "Termo de busca" }).fill(String(ticket.number))

    const opcao = page.getByRole("option", { name: new RegExp(`#${ticket.number}(\\D|$)`) })
    await expect(opcao).toBeVisible()
    await opcao.click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })

  test("termo de 1 caractere nao consulta o servidor", async ({ page, request }) => {
    await login(page, request, "admin")

    let chamadas = 0
    await page.route("**/api/busca**", (route) => {
      chamadas += 1
      return route.continue()
    })

    await page.keyboard.press("Control+k")
    const campo = page.getByRole("combobox", { name: "Termo de busca" })
    await campo.fill("a")
    await expect(page.getByText("Digite ao menos 2 caracteres")).toBeVisible()
    // espera bem alem do debounce (250ms) para provar ausencia de chamada, e
    // nao so a falta de tempo para ela acontecer.
    await page.waitForTimeout(600)
    expect(chamadas).toBe(0)

    // completa para 2 caracteres: agora o debounce dispara UMA chamada real,
    // provando que o gate de 1 caractere era mesmo a causa da ausencia acima.
    const resposta = page.waitForResponse(
      (res) => res.url().includes("/api/busca") && res.ok(),
    )
    await campo.fill("ab")
    await resposta
    expect(chamadas).toBe(1)
  })
})
