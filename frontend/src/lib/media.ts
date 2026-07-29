export type MediaKind = "imagem" | "pdf" | "video"

export const MAX_UPLOAD_BYTES = 52_428_800

const KINDS: Record<string, MediaKind> = {
  "image/jpeg": "imagem",
  "image/png": "imagem",
  "image/webp": "imagem",
  "application/pdf": "pdf",
  "video/mp4": "video",
  "video/quicktime": "video",
  "video/webm": "video",
}

export const ACCEPTED_MIME = Object.keys(KINDS)

const COMPRESS_ABOVE_BYTES = 2 * 1024 * 1024
const MAX_DIMENSION = 2000

export function kindOf(file: File): MediaKind | null {
  return KINDS[file.type] ?? null
}

async function loadImage(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error("falha ao decodificar imagem"))
      image.src = url
    })
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Reduz imagens grandes antes do upload. Em qualquer falha devolve o original:
 *  anexar a foto importa mais do que economizar bytes. */
export async function compressImage(file: File): Promise<File> {
  if (kindOf(file) !== "imagem") return file
  try {
    const image = await loadImage(file)
    const maior = Math.max(image.width, image.height)
    if (file.size <= COMPRESS_ABOVE_BYTES && maior <= MAX_DIMENSION) return file
    const escala = maior > MAX_DIMENSION ? MAX_DIMENSION / maior : 1
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(image.width * escala)
    canvas.height = Math.round(image.height * escala)
    const ctx = canvas.getContext("2d")
    if (!ctx) return file
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/webp", 0.82),
    )
    if (!blob || blob.size >= file.size) return file
    return new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.webp`, {
      type: "image/webp",
    })
  } catch {
    return file
  }
}

/** Captura um frame do video no proprio navegador (o servidor nao processa video). */
export async function captureVideoThumb(file: File): Promise<Blob | null> {
  if (kindOf(file) !== "video") return null
  const url = URL.createObjectURL(file)
  const video = document.createElement("video")
  video.muted = true
  video.playsInline = true
  video.preload = "metadata"
  try {
    const pronto = new Promise<void>((resolve, reject) => {
      const falhar = () => reject(new Error("codec sem suporte"))
      video.onerror = falhar
      video.onloadeddata = () => {
        video.currentTime = Math.min(1, (video.duration || 1) / 2)
      }
      video.onseeked = () => resolve()
      setTimeout(falhar, 8000)
    })
    video.src = url
    await pronto
    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext("2d")
    if (!ctx || !canvas.width || !canvas.height) return null
    ctx.drawImage(video, 0, 0)
    return await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/webp", 0.8),
    )
  } catch {
    return null
  } finally {
    URL.revokeObjectURL(url)
    video.removeAttribute("src")
  }
}
