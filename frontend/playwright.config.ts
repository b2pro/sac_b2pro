import { defineConfig, devices } from "@playwright/test"

// A porta e configuravel por E2E_PORT porque `reuseExistingServer` reaproveita
// qualquer servidor na porta: com 5173 ocupada por outro projeto, a suite roda
// contra o app errado em vez de falhar. `--strictPort` faz o Vite recusar a
// porta ocupada em vez de escorregar para a proxima.
const porta = process.env.E2E_PORT ?? "5173"
const baseURL = `http://localhost:${porta}`

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm dev --port ${porta} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
