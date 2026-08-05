import { expect, test } from "@playwright/test"

import { apiFullTicket, apiMarkAllNotificationsRead, login } from "./helpers"

// Padrao de dois contextos (ver "remover anexo aparece so para o autor ou
// quem decide" em 05-anexos.spec.ts): A e B precisam estar logados AO MESMO
// TEMPO em paginas separadas, porque a prova central deste teste e que o sino
// de B sobe sem ele recarregar nada -- reaproveitar uma unica pagina e trocar
// de sessao via login() ja seria um reload disfarcado.
test("comentario e transicao notificam o atendente ao vivo, o dropdown abre o ticket e marcar todas zera o sino", async ({
  browser,
  request,
}) => {
  // B = atendente e o atendente do ticket (apiFullTicket sem attendant_user_id
  // explicito atribui o proprio criador -- ver CreateTicketUseCase).
  const ticket = await apiFullTicket(request, "atendente")

  // Base conhecida: zera o que execucoes anteriores desta mesma suite possam
  // ter deixado nao lido para o atendente seedado, senao os contadores abaixo
  // teriam que ser relativos em vez de exatos.
  await apiMarkAllNotificationsRead(request, "atendente")

  const contextB = await browser.newContext()
  const pageB = await contextB.newPage()
  const contextA = await browser.newContext()
  const pageA = await contextA.newPage()

  try {
    // B entra primeiro e so avanca quando o stream SSE de fato abriu --
    // sinal de rede real (headers da resposta), nunca um sleep. Sem esperar
    // por isso, o comentario de A poderia chegar antes de B estar inscrito no
    // canal e o evento se perderia (o backend nao guarda evento para quem
    // ainda nao esta ouvindo).
    const streamAberto = pageB.waitForResponse(
      (res) => res.url().includes("/api/notificacoes/stream") && res.ok(),
    )
    await login(pageB, request, "atendente")
    await streamAberto

    // confirma a base zerada antes de A agir
    await expect(pageB.getByText(/notifica(cao|coes) nao lida/)).toHaveCount(0)

    // --- A (admin) comenta e depois envia o ticket para analise ---
    await login(pageA, request, "admin")
    await pageA.goto(`/tickets/${ticket.id}`)
    await pageA
      .getByPlaceholder("Escreva um comentario interno...")
      .fill("Confirmar nota fiscal antes de decidir.")
    await pageA.getByRole("button", { name: "Enviar", exact: true }).click()
    await expect(
      pageA.getByText("Confirmar nota fiscal antes de decidir."),
    ).toBeVisible()

    await pageA.getByRole("button", { name: "Enviar para analise" }).click()
    await expect(pageA.getByText("Aguardando analise").first()).toBeVisible()

    // --- B ve o sino subir para 2, SEM navegar nem recarregar a pagina ---
    await expect(pageB.getByText("2 notificacoes nao lidas")).toBeVisible()

    // --- abre o dropdown, ve o titulo da transicao (mais recente) e clica ---
    // O dropdown lista as ultimas 10 notificacoes independente de lida/nao
    // lida (so muda o estilo), entao o titulo generico sozinho pode casar
    // tambem uma notificacao ja lida de OUTRO ticket em execucoes anteriores
    // desta mesma suite -- o numero do ticket desambigua.
    await pageB.getByRole("button", { name: "Notificacoes" }).click()
    const itemTransicao = pageB.getByRole("menuitem", {
      name: new RegExp(`Ticket enviado para analise.*#${ticket.number}(\\D|$)`),
    })
    await expect(itemTransicao).toBeVisible()
    await itemTransicao.click()
    await expect(pageB).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))

    // sobrou so a notificacao do comentario: o sino cai para 1, nao para 0
    await expect(pageB.getByText("1 notificacao nao lida")).toBeVisible()

    // --- "marcar todas como lidas" zera o sino ---
    await pageB.getByRole("button", { name: "Notificacoes" }).click()
    await pageB.getByRole("menuitem", { name: "Marcar todas como lidas" }).click()
    await expect(pageB.getByText(/notifica(cao|coes) nao lida/)).toHaveCount(0)
  } finally {
    await contextA.close()
    await contextB.close()
  }
})
