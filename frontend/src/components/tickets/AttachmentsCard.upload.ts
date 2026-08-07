import { useCallback, useEffect, useRef, useState } from "react"

import { discardAttachmentIntent, uploadAttachment } from "@/lib/attachments"
import { kindOf, MAX_UPLOAD_BYTES } from "@/lib/media"

/** Fila de upload de anexos: um item por arquivo, processados em serie (um por
 *  vez) para nao competir por banda. Mantida fora do componente para o
 *  render ficar legivel — aqui so estado e a orquestracao de rede. */

export type FilaStatus = "aguardando" | "enviando" | "erro"

export type FilaItem = {
  id: string
  nome: string
  percent: number
  status: FilaStatus
  erro?: string
}

const CANCELADO = "upload cancelado"

/** Validacao no client antes de subir. Recusa no ato o que o servidor recusaria
 *  de qualquer forma — o servidor continua sendo a autoridade final. */
export function validarArquivo(arquivo: File): string | null {
  if (kindOf(arquivo) === null) return `${arquivo.name}: tipo não aceito`
  if (arquivo.size > MAX_UPLOAD_BYTES) return `${arquivo.name}: acima de 50 MB`
  return null
}

export function useUploadQueue(ticketId: string, onUploaded: () => void) {
  const [itens, setItens] = useState<FilaItem[]>([])
  const arquivos = useRef(new Map<string, File>())
  const controllers = useRef(new Map<string, AbortController>())
  // id do item na fila -> attachment_id que a intencao de upload criou no
  // servidor. Preenchido antes do PUT comecar (onIntent), porque um upload
  // abandonado nunca resolve e o id nao chegaria por outro caminho.
  const intents = useRef(new Map<string, string>())
  const pendentes = useRef<string[]>([])
  const processando = useRef(false)
  // itens com um descarte de intencao em voo. Sem esta trava, dois cliques em
  // "Tentar de novo" antes do primeiro render (clique duplo, ou touch duplicado)
  // entrariam duas vezes: o segundo veria o mapa de intents ja limpo, cairia no
  // caminho de "nunca teve intencao" e comecaria um segundo upload em paralelo.
  const retentando = useRef(new Set<string>())

  const atualizar = useCallback((id: string, patch: Partial<FilaItem>) => {
    setItens((atual) => atual.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }, [])

  const remover = useCallback((id: string) => {
    arquivos.current.delete(id)
    controllers.current.delete(id)
    setItens((atual) => atual.filter((item) => item.id !== id))
  }, [])

  /** Devolve ao ticket a vaga que a intencao de upload ocupou. A linha nasce
   *  `pendente` antes do PUT e conta na cota de 10 do servidor, mesmo invisivel
   *  na lista (que so mostra `disponivel`): sem este descarte, cada cancelamento
   *  ou nova tentativa queimaria uma vaga de forma silenciosa ate a varredura
   *  de 30 minutos do worker — e, com o worker parado, para sempre.
   *
   *  Quem decide e o servidor, nao o cliente: um upload cujo `confirmar` commitou
   *  mas cuja resposta se perdeu no caminho parece falha aqui, e um DELETE cego
   *  apagaria um anexo real. A rota de intencao recusa apagar o que ja esta
   *  disponivel e responde `disponivel`, entao `aoDescobrirConfirmado` avisa quem
   *  chamou que o upload deu certo. Falha de rede do proprio descarte e ignorada:
   *  a varredura do servidor resolve, e nao e assunto do usuario. */
  const descartarIntent = useCallback(
    (id: string, aoDescobrirConfirmado?: () => void) => {
      const attachmentId = intents.current.get(id)
      if (!attachmentId) return
      intents.current.delete(id)
      void discardAttachmentIntent(ticketId, attachmentId)
        .then((resultado) => {
          if (resultado.status === "disponivel") aoDescobrirConfirmado?.()
        })
        .catch(() => undefined)
    },
    [ticketId],
  )

  const processar = useCallback(async () => {
    if (processando.current) return
    processando.current = true
    try {
      let id: string | undefined
      while ((id = pendentes.current.shift())) {
        const arquivo = arquivos.current.get(id)
        if (!arquivo) continue
        const itemId = id
        const controller = new AbortController()
        controllers.current.set(itemId, controller)
        atualizar(itemId, { status: "enviando", percent: 0, erro: undefined })
        try {
          await uploadAttachment(ticketId, arquivo, {
            onIntent: (attachmentId) => intents.current.set(itemId, attachmentId),
            onProgress: (percent) => atualizar(itemId, { percent }),
            signal: controller.signal,
          })
          // confirmado: a linha virou um anexo de verdade e nao pode mais ser
          // descartada como intencao abandonada.
          intents.current.delete(itemId)
          remover(itemId)
          onUploaded()
        } catch (error) {
          controllers.current.delete(itemId)
          const mensagem = error instanceof Error ? error.message : "erro inesperado"
          if (mensagem === CANCELADO) {
            // cancelar acontece durante o PUT, antes do confirmar, entao o
            // normal e a vaga voltar; se o servidor disser que o anexo esta
            // disponivel, a listagem precisa mostra-lo.
            descartarIntent(itemId, onUploaded)
            remover(itemId)
          } else {
            // o intent fica no mapa: quem tentar de novo ou dispensar o item
            // libera a vaga (e sair da tela tambem, ver o cleanup abaixo).
            atualizar(itemId, { status: "erro", erro: mensagem })
          }
        }
      }
    } finally {
      processando.current = false
    }
  }, [ticketId, onUploaded, atualizar, remover, descartarIntent])

  /** Adiciona arquivos validos a fila e devolve as mensagens de rejeicao dos
   *  invalidos, para o componente exibir via toast. */
  const enfileirar = useCallback(
    (novosArquivos: File[]) => {
      const rejeitados: string[] = []
      const aceitos: FilaItem[] = []
      for (const arquivo of novosArquivos) {
        const erro = validarArquivo(arquivo)
        if (erro) {
          rejeitados.push(erro)
          continue
        }
        const id = crypto.randomUUID()
        arquivos.current.set(id, arquivo)
        pendentes.current.push(id)
        aceitos.push({ id, nome: arquivo.name, percent: 0, status: "aguardando" })
      }
      if (aceitos.length > 0) {
        setItens((atual) => [...atual, ...aceitos])
        void processar()
      }
      return rejeitados
    },
    [processar],
  )

  /** Cancela um item: aborta o upload em andamento ou, se ainda estiver so na
   *  fila (nao iniciado), remove antes de comecar. */
  const cancelar = useCallback(
    (id: string) => {
      const controller = controllers.current.get(id)
      if (controller) {
        controller.abort()
        return
      }
      const index = pendentes.current.indexOf(id)
      if (index !== -1) pendentes.current.splice(index, 1)
      remover(id)
    },
    [remover],
  )

  const reenfileirar = useCallback(
    (id: string) => {
      atualizar(id, { status: "aguardando", percent: 0, erro: undefined })
      pendentes.current.push(id)
      void processar()
    },
    [atualizar, processar],
  )

  const tentarNovamente = useCallback(
    (id: string) => {
      if (!arquivos.current.has(id)) return
      if (retentando.current.has(id)) return
      const attachmentId = intents.current.get(id)
      if (!attachmentId) {
        reenfileirar(id)
        return
      }
      // A tentativa anterior deixou uma linha pendente no servidor e o reenvio
      // pede uma intencao nova: sem descartar a anterior, cada nova tentativa do
      // mesmo arquivo consumiria mais uma vaga da cota do ticket. O reenvio
      // espera a resposta do descarte porque a tentativa anterior pode ter
      // commitado sem o cliente saber — nesse caso reenviar criaria um anexo
      // duplicado, quando o certo e mostrar o que ja existe.
      retentando.current.add(id)
      atualizar(id, { status: "aguardando", percent: 0, erro: undefined })
      void discardAttachmentIntent(ticketId, attachmentId)
        .then((resultado) => {
          // o destino da tentativa anterior agora e conhecido: o id nao serve mais
          intents.current.delete(id)
          retentando.current.delete(id)
          if (resultado.status === "disponivel") {
            remover(id)
            onUploaded()
            return
          }
          pendentes.current.push(id)
          void processar()
        })
        .catch(() => {
          // Sem resposta do descarte, o destino da tentativa anterior segue
          // desconhecido — a mesma ambiguidade que o `confirmar` tem. Reenviar as
          // cegas criaria um anexo duplicado, entao o attachment_id fica no mapa
          // e a proxima tentativa recomeca pelo descarte. Nao ha custo real em
          // esperar: com a API sem responder, o reenvio tambem nao completaria.
          retentando.current.delete(id)
          atualizar(id, { status: "erro", erro: "servidor não respondeu; tente de novo" })
        })
    },
    [ticketId, atualizar, processar, remover, onUploaded, reenfileirar],
  )

  const dispensar = useCallback(
    (id: string) => {
      descartarIntent(id, onUploaded)
      remover(id)
    },
    [remover, descartarIntent, onUploaded],
  )

  /** Sair da tela com upload em andamento (ou com um item em erro na fila) e
   *  mais um jeito de abandonar a intencao: aborta o que estiver em voo e
   *  devolve as vagas, em vez de deixa-las ocupadas ate a varredura do worker. */
  useEffect(
    () => () => {
      for (const controller of controllers.current.values()) controller.abort()
      for (const id of [...intents.current.keys()]) {
        // quem tem descarte em voo (tentarNovamente) ja esta devolvendo a vaga:
        // repetir aqui so mandaria um DELETE redundante, que perderia a corrida
        // e levaria 404.
        if (retentando.current.has(id)) continue
        descartarIntent(id)
      }
    },
    [descartarIntent],
  )

  return { itens, enfileirar, cancelar, tentarNovamente, dispensar }
}
