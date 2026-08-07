import { expect, test } from "@playwright/test"

import { API, apiFullTicket, login, token } from "./helpers"

/** Regressao da corrida entre o `confirmar` e o descarte da intencao.
 *
 *  O cliente nao sabe, quando o `confirmar` falha, se o servidor commitou ou
 *  nao: a resposta pode ter se perdido depois do commit. Enquanto o descarte era
 *  um DELETE cego no anexo, "Tentar de novo" apagava (soft-delete) um anexo real
 *  e reenviava, sem nada na tela. Agora o descarte passa pela rota de intencao,
 *  que recusa apagar o que ja esta disponivel e responde `disponivel` — o front
 *  entao mostra o anexo que existe em vez de reenviar.
 *
 *  A perda de resposta e simulada deixando a requisicao chegar ao servidor
 *  (route.fetch) e falhando so a resposta (route.abort): o commit acontece, o
 *  cliente ve erro de rede. */
test("confirmar que commitou sem resposta nao vira exclusao nem duplicata", async ({
  page,
  request,
}) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()

  // Conta os PUTs no storage para provar que nao houve reenvio: o caminho antigo
  // fazia dois (o original e o do retry), o novo faz um so.
  let putsNoStorage = 0
  await page.route(/:9000\//, async (route) => {
    if (route.request().method() === "PUT") putsNoStorage += 1
    await route.continue().catch(() => undefined)
  })

  // Um DELETE direto no anexo (sem /intencao) e exatamente o defeito: registra
  // para assertar que nao acontece.
  const exclusoesDiretas: string[] = []
  page.on("request", (req) => {
    if (req.method() === "DELETE" && /\/anexos\/[^/]+$/.test(new URL(req.url()).pathname)) {
      exclusoesDiretas.push(req.url())
    }
  })

  let confirmarPerdidos = 0
  await page.route(/\/anexos\/[^/]+\/confirmar$/, async (route) => {
    // so a primeira confirmacao se perde; um eventual reenvio seguiria normal
    if (confirmarPerdidos > 0) {
      await route.continue().catch(() => undefined)
      return
    }
    confirmarPerdidos += 1
    await route.fetch().catch(() => undefined)
    await route.abort().catch(() => undefined)
  })

  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/defeito.png")

  // O item cai em erro porque o cliente nao recebeu a resposta, mesmo o anexo
  // existindo no servidor — o estado confuso que o usuario ve.
  await expect(page.getByRole("button", { name: "Tentar de novo" })).toBeVisible({
    timeout: 20_000,
  })
  expect(confirmarPerdidos).toBe(1)

  // Espera qualquer DELETE de anexo, nao so o da intencao: se o front voltar a
  // pedir a exclusao direta, o teste falha aqui dizendo o que ele pediu, em vez
  // de esgotar o tempo esperando uma requisicao que nunca vem.
  const descarte = page.waitForResponse(
    (res) => res.request().method() === "DELETE" && res.url().includes("/anexos/"),
  )
  await page.getByRole("button", { name: "Tentar de novo" }).click()
  const resposta = await descarte
  expect(new URL(resposta.url()).pathname).toMatch(/\/anexos\/[^/]+\/intencao$/)
  expect(await resposta.json()).toEqual({ status: "disponivel" })

  // O anexo real sobrevive, aparece uma unica vez e a fila esvazia sem erro.
  await expect(page.locator('button[title="defeito.png"]')).toHaveCount(1, { timeout: 20_000 })
  await expect(page.getByRole("button", { name: "Tentar de novo" })).toHaveCount(0)
  expect(putsNoStorage).toBe(1)
  expect(exclusoesDiretas).toEqual([])
})

/** A mesma ambiguidade um nivel acima: se a resposta do DESCARTE se perder, o
 *  destino da tentativa anterior segue desconhecido. Reenviar as cegas ai criaria
 *  um anexo duplicado — o item precisa voltar para erro e a proxima tentativa
 *  recomecar pelo descarte. */
test("descarte sem resposta nao reenvia as cegas", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()

  let putsNoStorage = 0
  await page.route(/:9000\//, async (route) => {
    if (route.request().method() === "PUT") putsNoStorage += 1
    await route.continue().catch(() => undefined)
  })

  await page.route(/\/anexos\/[^/]+\/confirmar$/, async (route) => {
    await route.fetch().catch(() => undefined)
    await route.abort().catch(() => undefined)
  })
  // o servidor decide o descarte, o cliente nao recebe a decisao
  let descartesPerdidos = 0
  await page.route(/\/anexos\/[^/]+\/intencao$/, async (route) => {
    descartesPerdidos += 1
    await route.fetch().catch(() => undefined)
    await route.abort().catch(() => undefined)
  })

  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/defeito.png")
  await expect(page.getByRole("button", { name: "Tentar de novo" })).toBeVisible({
    timeout: 20_000,
  })

  await page.getByRole("button", { name: "Tentar de novo" }).click()

  await expect(page.getByText("servidor não respondeu; tente de novo")).toBeVisible({
    timeout: 20_000,
  })
  expect(descartesPerdidos).toBe(1)
  // nada foi reenviado: um unico PUT no storage
  expect(putsNoStorage).toBe(1)

  // O servidor e a fonte da verdade aqui: a UI nao refaz a listagem no caminho
  // ambiguo (nao ha sucesso a declarar), entao a prova de "nao apagou e nao
  // duplicou" e o estado no servidor — exatamente um anexo.
  const autenticado = { Authorization: `Bearer ${await token(request, "admin")}` }
  const anexos = await (
    await request.get(`${API}/tickets/${ticket.id}/anexos`, { headers: autenticado })
  ).json()
  expect(anexos).toHaveLength(1)
})

/** Dois cliques em "Tentar de novo" antes do primeiro render. O botao sai da tela
 *  na primeira mudanca de estado, entao a reentrancia so acontece dentro do mesmo
 *  ciclo — reproduzida chamando .click() duas vezes na mesma tarefa. */
test("clique duplo em tentar de novo dispara um descarte so", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()

  let putsNoStorage = 0
  await page.route(/:9000\//, async (route) => {
    if (route.request().method() === "PUT") putsNoStorage += 1
    await route.continue().catch(() => undefined)
  })
  let descartes = 0
  page.on("request", (req) => {
    if (req.method() === "DELETE" && req.url().includes("/intencao")) descartes += 1
  })

  let primeiroConfirmar = true
  await page.route(/\/anexos\/[^/]+\/confirmar$/, async (route) => {
    if (!primeiroConfirmar) {
      await route.continue().catch(() => undefined)
      return
    }
    primeiroConfirmar = false
    await route.fetch().catch(() => undefined)
    await route.abort().catch(() => undefined)
  })

  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/defeito.png")
  await expect(page.getByRole("button", { name: "Tentar de novo" })).toBeVisible({
    timeout: 20_000,
  })

  await page.evaluate(() => {
    const botao = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "Tentar de novo",
    )
    botao?.click()
    botao?.click()
  })

  await expect(page.locator('button[title="defeito.png"]')).toHaveCount(1, { timeout: 20_000 })
  expect(descartes).toBe(1)
  expect(putsNoStorage).toBe(1)
})
