import { api } from "@/lib/api"
import { captureVideoThumb, compressImage, kindOf, type MediaKind } from "@/lib/media"

export type Attachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  kind: MediaKind
  preview_status: "sem_preview" | "pendente" | "pronto" | "falhou"
  preview_url: string | null
  author_user_id: string
  author_name: string | null
  created_at: string | null
}

export type AttachmentIntent = {
  attachment_id: string
  object_key: string
  upload_url: string
  expires_in: number
  preview_upload_url: string | null
}

export type UploadProgress = (percent: number) => void

type IntentBody = {
  filename: string
  content_type: string
  size_bytes: number
  with_preview?: boolean
}

export const requestIntent = (ticketId: string, body: IntentBody) =>
  api<AttachmentIntent>(`/tickets/${ticketId}/anexos/intencao`, {
    method: "POST",
    body,
  })

export const confirmUpload = (ticketId: string, attachmentId: string) =>
  api<Attachment>(`/tickets/${ticketId}/anexos/${attachmentId}/confirmar`, {
    method: "POST",
  })

export const listAttachments = (ticketId: string) =>
  api<Attachment[]>(`/tickets/${ticketId}/anexos`)

export const attachmentUrl = (
  ticketId: string,
  attachmentId: string,
  variante: "medio" | "original" = "medio",
) =>
  api<{ url: string; expires_in: number }>(
    `/tickets/${ticketId}/anexos/${attachmentId}/url?variante=${variante}`,
  )

export const deleteAttachment = (ticketId: string, attachmentId: string) =>
  api<void>(`/tickets/${ticketId}/anexos/${attachmentId}`, { method: "DELETE" })

/** PUT direto no storage. Usa XMLHttpRequest porque fetch nao reporta progresso
 *  de upload. A URL ja vem assinada; nao acrescentar headers de autenticacao.
 *  Aceita um AbortSignal opcional para cancelamento (ex.: fila de upload da UI);
 *  um signal ja abortado antes de comecar tambem e respeitado. */
export function putToStorage(
  url: string,
  body: Blob,
  contentType: string,
  onProgress?: UploadProgress,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("upload cancelado"))
      return
    }
    const xhr = new XMLHttpRequest()
    const onSignalAbort = () => xhr.abort()
    const cleanup = () => signal?.removeEventListener("abort", onSignalAbort)
    xhr.open("PUT", url)
    xhr.setRequestHeader("Content-Type", contentType)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      cleanup()
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`falha no upload (${xhr.status})`))
    }
    xhr.onerror = () => {
      cleanup()
      reject(new Error("falha de rede no upload"))
    }
    xhr.onabort = () => {
      cleanup()
      reject(new Error("upload cancelado"))
    }
    signal?.addEventListener("abort", onSignalAbort)
    xhr.send(body)
  })
}

export async function uploadAttachment(
  ticketId: string,
  file: File,
  onProgress?: UploadProgress,
  signal?: AbortSignal,
): Promise<Attachment> {
  const preparado = await compressImage(file)
  const thumb = await captureVideoThumb(preparado)
  const intent = await requestIntent(ticketId, {
    filename: preparado.name,
    content_type: preparado.type,
    size_bytes: preparado.size,
    with_preview: thumb !== null,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress, signal)
  if (thumb && intent.preview_upload_url) {
    try {
      await putToStorage(intent.preview_upload_url, thumb, "image/webp", undefined, signal)
    } catch (error) {
      // Cancelamento do usuario nao pode ser absorvido aqui: se o signal foi
      // abortado, o upload inteiro deve ser reportado como cancelado, nao como
      // sucesso. Qualquer outra falha do thumb continua tolerada — e best-effort,
      // o backend cai para sem_preview se o thumb nao chegar, e isso nunca deve
      // impedir a confirmacao do anexo ja enviado.
      if (signal?.aborted) throw error
    }
  }
  return confirmUpload(ticketId, intent.attachment_id)
}

export type PhotoIntent = { object_key: string; upload_url: string; expires_in: number }

export const requestProductPhotoIntent = (
  productId: string,
  body: { content_type: string; size_bytes: number },
) =>
  api<PhotoIntent>(`/cadastros/produtos/${productId}/foto/intencao`, {
    method: "POST",
    body,
  })

export const confirmProductPhoto = (productId: string, objectKey: string) =>
  api<void>(`/cadastros/produtos/${productId}/foto/confirmar`, {
    method: "POST",
    body: { object_key: objectKey },
  })

export const deleteProductPhoto = (productId: string) =>
  api<void>(`/cadastros/produtos/${productId}/foto`, { method: "DELETE" })

export async function uploadProductPhoto(
  productId: string,
  file: File,
  onProgress?: UploadProgress,
  signal?: AbortSignal,
): Promise<void> {
  if (kindOf(file) !== "imagem") throw new Error("a foto do produto precisa ser imagem")
  const preparado = await compressImage(file)
  const intent = await requestProductPhotoIntent(productId, {
    content_type: preparado.type,
    size_bytes: preparado.size,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress, signal)
  await confirmProductPhoto(productId, intent.object_key)
}
