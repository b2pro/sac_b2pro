import { randomBytes } from "node:crypto"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"

import { expect, test } from "@playwright/test"

import {
  apiCreateProduct,
  apiFullTicket,
  apiProductPhotoKey,
  login,
} from "./helpers"

/** Playwright recusa buffers acima de 50 MB em setInputFiles ("Cannot set
 *  buffer larger than 50Mb"), entao o arquivo grande de teste precisa existir
 *  em disco. Gerado fora de e2e/fixtures (nao versionado) e apagado ao final. */
function arquivoGrande(): string {
  const dir = mkdtempSync(join(tmpdir(), "sac-e2e-"))
  const caminho = join(dir, "grande.png")
  writeFileSync(caminho, randomBytes(51 * 1024 * 1024))
  return caminho
}

test("anexa imagem pelo dropzone, aguarda o preview assincrono e remove", async ({
  page,
  request,
}) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)

  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/defeito.png")

  await expect(page.getByText("defeito.png")).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText("Nenhum anexo neste ticket.")).toHaveCount(0)

  // O preview de imagem e gerado pelo worker (fila preview_jobs), fora do
  // processo do navegador: RequestUploadUseCase ja grava o anexo como
  // preview_status "pendente" na intencao de upload, antes mesmo do arquivo
  // chegar ao storage, e o card so troca o spinner por uma <img> quando o
  // worker processa o job e a lista repolla (AttachmentsCard refetcha a cada
  // 4s enquanto houver pendente). Sem o worker de pe esta espera estoura o
  // timeout de proposito: um teste que passasse sem o worker rodando nao
  // provaria que a Fase 2B entrega o preview assincrono.
  const tile = page.locator('button[title="defeito.png"]')
  await expect(tile.locator("img")).toBeVisible({ timeout: 45_000 })

  await page.getByRole("button", { name: "Acoes do anexo defeito.png" }).click()
  await page.getByRole("menuitem", { name: "Remover" }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Remover" }).click()
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()
})

test("visualizador ve anexos sem dropzone", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "viewer")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Anexos")).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
})

test("recusa tipo invalido e arquivo acima do limite no dropzone", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)

  const input = page.locator('input[type="file"]')

  // tipo nao aceito: recusado no client, nunca chega a pedir intencao de upload
  await input.setInputFiles({
    name: "relatorio.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("conteudo de teste"),
  })
  await expect(page.getByText(/relatorio\.txt: tipo nao aceito/)).toBeVisible()
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()

  // acima de 50 MB: tipo valido, tamanho que estoura o limite
  const grande = arquivoGrande()
  try {
    await input.setInputFiles(grande)
    await expect(page.getByText(/grande\.png: acima de 50 MB/)).toBeVisible()
    await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()
  } finally {
    rmSync(dirname(grande), { force: true, recursive: true })
  }
})

test("remover foto do produto exige confirmacao antes de excluir", async ({ page, request }) => {
  const unico = Date.now()
  const produto = await apiCreateProduct(request, "admin", {
    name: `Produto Foto ${unico}`,
    sku: `E2E-FOTO-${unico}`,
  })

  await login(page, request, "admin")
  await page.goto("/cadastros/produtos")
  await page.getByPlaceholder("Buscar por nome ou SKU").fill(produto.sku)
  await page
    .getByRole("row")
    .filter({ hasText: produto.sku })
    .getByRole("button", { name: "Editar" })
    .click()

  const dialogEdicao = page.getByRole("dialog", { name: "Editar produto" })
  await dialogEdicao.locator("#edit-foto").setInputFiles("e2e/fixtures/defeito.png")
  await expect(page.getByText("Foto enviada")).toBeVisible({ timeout: 20_000 })
  await expect(dialogEdicao.getByRole("button", { name: "Remover foto" })).toBeVisible()

  // clicar em "Remover foto" so abre o dialog de confirmacao - nao apaga na hora
  await dialogEdicao.getByRole("button", { name: "Remover foto" }).click()
  const confirmacao = page.getByRole("dialog", { name: "Remover foto" })
  await expect(confirmacao).toBeVisible()

  // cancelar tem que deixar a foto intacta - conferido direto no backend (nao
  // so na UI), pra provar que o cancelar nao disparou o DELETE por baixo
  await confirmacao.getByRole("button", { name: "Cancelar" }).click()
  await expect(confirmacao).toBeHidden()
  expect(await apiProductPhotoKey(request, produto.sku)).not.toBeNull()
  await expect(dialogEdicao.getByRole("button", { name: "Remover foto" })).toBeVisible()

  // agora confirmando de verdade: a foto sai
  await dialogEdicao.getByRole("button", { name: "Remover foto" }).click()
  await confirmacao.getByRole("button", { name: "Remover" }).click()
  await expect(page.getByText("Foto removida")).toBeVisible()
  await expect(dialogEdicao.getByRole("button", { name: "Remover foto" })).toHaveCount(0)
  expect(await apiProductPhotoKey(request, produto.sku)).toBeNull()
})

test("upload de foto de um produto nao aparece no dialog de outro produto", async ({
  page,
  request,
}) => {
  const unico = Date.now()
  const produtoA = await apiCreateProduct(request, "admin", {
    name: `Produto A ${unico}`,
    sku: `E2E-A-${unico}`,
  })
  const produtoB = await apiCreateProduct(request, "admin", {
    name: `Produto B ${unico}`,
    sku: `E2E-B-${unico}`,
  })

  await login(page, request, "admin")
  await page.goto("/cadastros/produtos")

  // Segura a confirmacao do upload da foto do produto A no servidor: da tempo
  // de fechar o dialog de A e abrir o de B com o upload de A ainda "em voo",
  // sem depender da velocidade real da rede local (que tende a ser rapida
  // demais para pegar essa janela de outro jeito). photoMutation.isPending
  // fica true desde a chamada de .mutate(), entao o texto "Enviando..." ja
  // aparece antes mesmo do PUT no storage comecar - so precisamos que a
  // mutacao continue pendente ate depois de trocar de produto.
  let liberarConfirmacao: (() => void) | undefined
  const confirmacaoPresa = new Promise<void>((resolve) => {
    liberarConfirmacao = resolve
  })
  await page.route("**/foto/confirmar", async (route) => {
    await confirmacaoPresa
    await route.continue()
  })

  await page.getByPlaceholder("Buscar por nome ou SKU").fill(produtoA.sku)
  await page
    .getByRole("row")
    .filter({ hasText: produtoA.sku })
    .getByRole("button", { name: "Editar" })
    .click()
  const dialogEdicao = page.getByRole("dialog", { name: "Editar produto" })
  await dialogEdicao.locator("#edit-foto").setInputFiles("e2e/fixtures/defeito.png")
  await expect(dialogEdicao.getByText(/Enviando\.\.\./)).toBeVisible()

  await page.keyboard.press("Escape")
  await expect(dialogEdicao).toBeHidden()

  await page.getByPlaceholder("Buscar por nome ou SKU").fill(produtoB.sku)
  await page
    .getByRole("row")
    .filter({ hasText: produtoB.sku })
    .getByRole("button", { name: "Editar" })
    .click()
  const dialogB = page.getByRole("dialog", { name: "Editar produto" })
  await expect(dialogB).toBeVisible()
  await expect(dialogB.getByText(/Enviando\.\.\./)).toHaveCount(0)

  liberarConfirmacao?.()
})
