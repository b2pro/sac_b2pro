import { api, apiRaw } from "@/lib/api"

export type NotificationType = "atribuicao" | "transicao" | "comentario"

/** Espelho de NotificationOut (backend). */
export type NotificationItem = {
  id: string
  ticket_id: string
  ticket_number: number
  type: NotificationType
  title: string
  snippet: string | null
  created_at: string
  read_at: string | null
}

export type NotificationsPage = { items: NotificationItem[]; total: number }

export type NotificationCounter = { nao_lidas: number }

/** Quantas notificacoes o sino mostra — o dropdown nao pagina, quem quer o
 *  historico completo abre o ticket. */
const PER_PAGE = 10

export function fetchNotifications(page = 1, apenasNaoLidas = false): Promise<NotificationsPage> {
  const search = new URLSearchParams({
    apenas_nao_lidas: String(apenasNaoLidas),
    page: String(page),
    per_page: String(PER_PAGE),
  })
  return api<NotificationsPage>(`/notificacoes?${search.toString()}`)
}

export function fetchCounter(): Promise<NotificationCounter> {
  return api<NotificationCounter>("/notificacoes/contador")
}

/** `null` marca todas como lidas. */
export function markRead(ids: string[] | null): Promise<void> {
  return api<void>("/notificacoes/marcar-lidas", { method: "POST", body: { ids } })
}

const RECONNECT_MIN_MS = 1_000
const RECONNECT_MAX_MS = 30_000
// O servidor manda "`: ping`" a cada 25s, entao passar de dois heartbeats sem
// frame algum significa conexao morta. Nem toda morte chega como erro: proxy,
// NAT ou maquina que dormiu deixam o socket aberto sem nunca mais entregar nada
// e a leitura fica pendurada para sempre — sem este limite o sino ficaria mudo
// ate o proximo reload.
const IDLE_TIMEOUT_MS = 60_000
// Teto da linha em montagem. Frame deste stream tem dezenas de caracteres, entao
// 64k sem um "\n" nao e linha grande: e resposta malformada. Sem o teto o buffer
// cresceria sem limite e o watchdog nao salvaria, porque byte ESTA chegando.
const MAX_LINE_LENGTH = 65_536

/** Le o corpo SSE linha a linha e chama `onEvent` a cada bloco de evento.
 *
 *  O framing importa: um evento termina em linha vazia, uma linha pode chegar
 *  partida entre dois chunks (por isso o buffer) e linha comecando com ":" e
 *  comentario — o heartbeat do servidor ("`: ping`") passa por aqui e nao pode
 *  virar evento, mas conta como prova de que do outro lado ha um servidor de
 *  eventos vivo, por isso `onServerFrame`. O conteudo do `data:` e ignorado de
 *  proposito: o evento e so sinal, quem tem a verdade e a tabela, que o cliente
 *  reconsulta.
 *
 *  Lanca se a linha em montagem passar de `MAX_LINE_LENGTH` — quem chamou trata
 *  como conexao ruim e cai no backoff. */
async function readEventStream(
  body: NonNullable<Response["body"]>,
  handlers: { onEvent: () => void; onServerFrame: () => void },
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let hasData = false
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let breakAt = buffer.indexOf("\n")
    while (breakAt !== -1) {
      const line = buffer.slice(0, breakAt).replace(/\r$/, "")
      buffer = buffer.slice(breakAt + 1)
      if (line === "") {
        if (hasData) {
          hasData = false
          handlers.onEvent()
        }
      } else if (line.startsWith("data:")) {
        hasData = true
        handlers.onServerFrame()
      } else if (line.startsWith(":")) {
        // comentario/heartbeat: nao e evento, mas e sinal de vida
        handlers.onServerFrame()
      }
      breakAt = buffer.indexOf("\n")
    }
    if (buffer.length > MAX_LINE_LENGTH) throw new Error("linha SSE sem fim")
  }
}

/** Abre o stream de notificacoes e chama `onEvent` a cada evento recebido.
 *  Devolve o cleanup, que aborta a conexao e cancela a reconexao pendente.
 *
 *  Usa `fetch` (via `apiRaw`) e nao `EventSource`: o endpoint exige
 *  `Authorization: Bearer` e a API nativa nao envia header — de brinde vem o
 *  refresh-and-retry do `apiRaw` no 401. Queda de conexao reconecta com backoff
 *  de 1s a 30s, que so volta ao minimo depois de a conexao entregar um frame
 *  SSE; conexao que passa de `IDLE_TIMEOUT_MS` sem frame (nem os heartbeats
 *  chegam) e cortada para reabrir; resposta 4xx encerra o loop, porque nao ha o
 *  que reconectar quando a sessao ou o tenant do token nao servem. */
export function startNotificationStream(onEvent: () => void): () => void {
  let stopped = false
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let delayMs = RECONNECT_MIN_MS

  function scheduleReconnect(): void {
    if (stopped) return
    timer = setTimeout(() => void connect(), delayMs)
    delayMs = Math.min(delayMs * 2, RECONNECT_MAX_MS)
  }

  async function connect(): Promise<void> {
    if (stopped) return
    const connection = new AbortController()
    controller = connection
    // vale tambem para o aperto de mao: servidor que aceita o socket e nunca
    // responde os headers deixaria o await pendurado sem o watchdog
    let watchdog: ReturnType<typeof setTimeout> | undefined
    const armWatchdog = () => {
      if (watchdog) clearTimeout(watchdog)
      watchdog = setTimeout(() => connection.abort(), IDLE_TIMEOUT_MS)
    }
    try {
      armWatchdog()
      const res = await apiRaw("/notificacoes/stream", { signal: connection.signal })
      if (res.status >= 400 && res.status < 500) return
      if (!res.ok || !res.body) {
        scheduleReconnect()
        return
      }
      await readEventStream(res.body, {
        onEvent: () => {
          if (!stopped) onEvent()
        },
        // So o frame SSE zera o backoff, nunca o 200 nos headers: upstream que
        // aceita e encerra o corpo na hora deixaria toda tentativa "bem
        // sucedida", e o backoff nunca sairia de 1s — uma requisicao por segundo
        // por aba aberta, para sempre. Provar que entrega frame e o que compra o
        // retry rapido; o mesmo frame rearma o watchdog.
        onServerFrame: () => {
          delayMs = RECONNECT_MIN_MS
          armWatchdog()
        },
      })
      // o corpo terminou sem erro: o servidor fechou o stream, reabrir
      scheduleReconnect()
    } catch {
      // rede caiu, servidor sumiu, o watchdog cortou a conexao muda ou o
      // cleanup abortou — no ultimo caso `stopped` barra o reagendamento
      scheduleReconnect()
    } finally {
      if (watchdog) clearTimeout(watchdog)
    }
  }

  void connect()

  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
    controller?.abort()
  }
}

let audioContext: AudioContext | null = null

/** Beep curto de ~200ms gerado com WebAudio, sem asset binario e sem
 *  dependencia nova. Falha em silencio: o som e acessorio e o navegador pode
 *  bloquear audio antes da primeira interacao do usuario — nesse caso este
 *  aviso e perdido de proposito (ver abaixo) e o proximo toca. */
export function playNotificationBeep(): void {
  try {
    audioContext ??= new AudioContext()
    const ctx = audioContext
    if (ctx.state === "suspended") {
      // Contexto bloqueado: o navegador exige um gesto do usuario na aba antes
      // de deixar tocar audio. Pede a retomada (que fica pendente ate o gesto)
      // e DESISTE deste aviso, em vez de agendar o oscilador. Agendar seria
      // pior que o silencio: com o contexto suspenso `currentTime` fica parado
      // em 0, o `start(0)`/`stop(0.21)` ficariam na fila e tocariam no instante
      // em que o usuario clicasse em qualquer coisa — um bipe atrasado, as
      // vezes minutos depois, anunciando notificacao que ele ja leu. Do proximo
      // aviso em diante o contexto ja esta rodando e o bipe sai na hora.
      // O `.catch` cobre engine que rejeita `resume()`, que sem ele viraria
      // "Uncaught (in promise)" no console.
      ctx.resume().catch(() => {})
      return
    }
    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    const start = ctx.currentTime
    oscillator.type = "sine"
    oscillator.frequency.value = 880
    // envelope curto: sem o ramp o corte seco estala no alto-falante
    gain.gain.setValueAtTime(0, start)
    gain.gain.linearRampToValueAtTime(0.06, start + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.2)
    oscillator.connect(gain)
    gain.connect(ctx.destination)
    oscillator.start(start)
    oscillator.stop(start + 0.21)
  } catch {
    // sem audio disponivel: ignora
  }
}
