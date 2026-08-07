import { expect, test } from "@playwright/test"

import {
  apiGetPreferences,
  apiSavePreferences,
  login,
  loginViaFormRetrying,
  randomEmail,
  selectOption,
  USERS,
  type ApiPreferences,
} from "./helpers"

test.describe("Preferencias e membros", () => {
  test("trocar para escuro poe a classe dark no html e persiste apos reload", async ({
    page,
    request,
  }) => {
    const original: ApiPreferences = await apiGetPreferences(request, "viewer")
    // base conhecida ("claro"): se uma execucao anterior tivesse deixado
    // "escuro" gravado, clicar no radio "Escuro" ja marcado nao dispara
    // onChange (o navegador so avisa mudanca de valor) e o teste "passaria"
    // sem provar nada.
    await apiSavePreferences(request, "viewer", { ...original, theme: "claro" })

    try {
      await login(page, request, "viewer")
      await page.goto("/preferencias")
      await expect(page.getByRole("heading", { name: "Preferências" })).toBeVisible()
      await expect(page.locator("html")).not.toHaveClass(/dark/)

      await page.getByRole("radio", { name: "Escuro" }).click()
      await expect(page.locator("html")).toHaveClass(/dark/)
      // espera o PUT confirmar antes de recarregar: sem isto, o reload poderia
      // acontecer antes do servidor gravar e o teste "provaria" persistencia
      // que na verdade nao aconteceu ainda.
      await expect(page.getByText("Preferências salvas")).toBeVisible()

      await page.reload()
      await expect(page.locator("html")).toHaveClass(/dark/)
    } finally {
      // devolve a preferencia ao valor de antes: tema e conta global do
      // usuario seedado, persiste entre execucoes e nao pode ficar dependendo
      // deste teste ter rodado.
      await apiSavePreferences(request, "viewer", original)
    }
  })

  test("admin cria membro novo e o membro entra com as credenciais criadas", async ({
    page,
    request,
  }) => {
    const email = randomEmail("e2e-membro")
    const senha = "senha-membro-2026"
    const nome = "Membro Criado E2E"

    await login(page, request, "admin")
    await page.goto("/membros")
    await expect(page.getByRole("heading", { name: "Membros", level: 1 })).toBeVisible()

    await page.getByRole("button", { name: "Novo membro" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()

    // Papel != default (atendente): prova que a escolha do Select realmente
    // chega ao servidor, e nao so que o formulario aceita o valor inicial.
    await selectOption(page, "membro-papel", "Visualizador")
    await dialog.getByLabel("Nome").fill(nome)
    await dialog.getByLabel("Email").fill(email)
    // getByLabel("Senha") sem escopo colide com "Redefinir senha de <nome>"
    // das linhas da tabela (substring "senha" no aria-label do botao) —
    // escopar em `dialog` evita a colisao.
    await dialog.getByLabel("Senha").fill(senha)
    await dialog.getByRole("button", { name: "Cadastrar membro" }).click()

    await expect(dialog).toHaveCount(0)
    const linha = page.getByRole("row", { name: new RegExp(email) })
    await expect(linha).toBeVisible()
    await expect(linha).toContainText("Visualizador")

    await page.getByRole("button", { name: USERS.admin.name }).click()
    await page.getByRole("menuitem", { name: "Sair" }).click()
    await expect(page).toHaveURL(/\/login$/)

    // login novo, fora do cache de sessoes de USERS: conta contra o rate
    // limit de 5/min por IP+tenant, entao segue com retry em 429.
    await loginViaFormRetrying(page, email, senha)
  })

  test("supervisor nao ve o item Membros no menu nem alcanca a rota navegando direto", async ({
    page,
    request,
  }) => {
    await login(page, request, "supervisor")
    await expect(page.getByRole("link", { name: "Membros" })).toHaveCount(0)

    // RequireAdmin (main.tsx / guards.tsx) recusa a rota antes da pagina
    // montar: quem nao e admin e mandado para "/", que o HomeRedirect leva
    // para o dashboard do tenant ativo — nunca chega a montar a tela nem a
    // chamar a API de gerencia.
    await page.goto("/membros")
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole("heading", { name: "Membros", level: 1 })).toHaveCount(0)
  })
})
