import { useCallback, useRef, useState } from "react"

import { uploadAttachment } from "@/lib/attachments"
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
          await uploadAttachment(
            ticketId,
            arquivo,
            (percent) => atualizar(itemId, { percent }),
            controller.signal,
          )
          remover(itemId)
          onUploaded()
        } catch (error) {
          controllers.current.delete(itemId)
          const mensagem = error instanceof Error ? error.message : "erro inesperado"
          if (mensagem === CANCELADO) {
            remover(itemId)
          } else {
            atualizar(itemId, { status: "erro", erro: mensagem })
          }
        }
      }
    } finally {
      processando.current = false
    }
  }, [ticketId, onUploaded, atualizar, remover])

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
      atualizar(id, { status: "aguardando", percent: 0, erro: undefined })
      pendentes.current.push(id)
      void processar()
    },
    [atualizar, processar],
  )

  const dispensar = useCallback((id: string) => remover(id), [remover])

  return { itens, enfileirar, cancelar, tentarNovamente, dispensar }
}
