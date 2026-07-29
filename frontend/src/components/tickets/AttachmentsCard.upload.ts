import { useCallback, useEffect, useRef, useState } from "react"

import { deleteAttachment, uploadAttachment } from "@/lib/attachments"
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
  if (kindOf(arquivo) === null) return `${arquivo.name}: tipo nao aceito`
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
   *  na lista (que so mostra `disponivel`): sem este DELETE, cada cancelamento
   *  ou nova tentativa queimaria uma vaga de forma silenciosa ate a varredura
   *  de 30 minutos do worker — e, com o worker parado, para sempre. Falha do
   *  DELETE e ignorada de proposito: 404 ou corrida com o servidor nao e
   *  assunto do usuario. */
  const descartarIntent = useCallback(
    (id: string) => {
      const attachmentId = intents.current.get(id)
      if (!attachmentId) return
      intents.current.delete(id)
      void deleteAttachment(ticketId, attachmentId).catch(() => undefined)
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
            descartarIntent(itemId)
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

  const tentarNovamente = useCallback(
    (id: string) => {
      if (!arquivos.current.has(id)) return
      // a tentativa anterior deixou uma linha pendente no servidor e o reenvio
      // pede uma intencao nova: sem descartar a anterior, cada nova tentativa
      // do mesmo arquivo consumiria mais uma vaga da cota do ticket.
      descartarIntent(id)
      atualizar(id, { status: "aguardando", percent: 0, erro: undefined })
      pendentes.current.push(id)
      void processar()
    },
    [atualizar, processar, descartarIntent],
  )

  const dispensar = useCallback(
    (id: string) => {
      descartarIntent(id)
      remover(id)
    },
    [remover, descartarIntent],
  )

  /** Sair da tela com upload em andamento (ou com um item em erro na fila) e
   *  mais um jeito de abandonar a intencao: aborta o que estiver em voo e
   *  devolve as vagas, em vez de deixa-las ocupadas ate a varredura do worker. */
  useEffect(
    () => () => {
      for (const controller of controllers.current.values()) controller.abort()
      for (const id of [...intents.current.keys()]) descartarIntent(id)
    },
    [descartarIntent],
  )

  return { itens, enfileirar, cancelar, tentarNovamente, dispensar }
}
