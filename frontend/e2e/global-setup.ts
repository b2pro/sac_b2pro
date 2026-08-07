import { request as apiRequest } from "@playwright/test"

import { ensureCatalogoBase } from "./helpers"

/**
 * Deixa o tenant e2e com o cenario base antes do primeiro teste.
 *
 * O provisionamento de tenant nao semeia catalogo nenhum (ver
 * backend/src/sac/infrastructure/tenant_seeds.py), e boa parte dos specs escolhe
 * marca e canal pelo nome direto na UI -- nao da para resolver isso dentro de um
 * helper de API, porque nenhum helper e chamado antes daquele clique.
 *
 * Roda uma vez por execucao e e idempotente: num tenant que ja tem os registros,
 * so faz leitura. O custo e um login de admin, que cabe no limite de 5 por
 * minuto por IP+tenant (e o `requestSession` ainda repete em 429).
 */
export default async function globalSetup(): Promise<void> {
  const context = await apiRequest.newContext()
  try {
    await ensureCatalogoBase(context)
  } finally {
    await context.dispose()
  }
}
