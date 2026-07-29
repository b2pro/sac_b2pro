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
 *  de upload. A URL ja vem assinada; nao acrescentar headers de autenticacao. */
export function putToStorage(
  url: string,
  body: Blob,
  contentType: string,
  onProgress?: UploadProgress,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    xhr.setRequestHeader("Content-Type", contentType)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`falha no upload (${xhr.status})`))
    xhr.onerror = () => reject(new Error("falha de rede no upload"))
    xhr.send(body)
  })
}

export async function uploadAttachment(
  ticketId: string,
  file: File,
  onProgress?: UploadProgress,
): Promise<Attachment> {
  const preparado = await compressImage(file)
  const thumb = await captureVideoThumb(preparado)
  const intent = await requestIntent(ticketId, {
    filename: preparado.name,
    content_type: preparado.type,
    size_bytes: preparado.size,
    with_preview: thumb !== null,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress)
  if (thumb && intent.preview_upload_url) {
    await putToStorage(intent.preview_upload_url, thumb, "image/webp")
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
): Promise<void> {
  if (kindOf(file) !== "imagem") throw new Error("a foto do produto precisa ser imagem")
  const preparado = await compressImage(file)
  const intent = await requestProductPhotoIntent(productId, {
    content_type: preparado.type,
    size_bytes: preparado.size,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress)
  await confirmProductPhoto(productId, intent.object_key)
}
