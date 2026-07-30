import { Download, Loader2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"

export function ExportCsvButton({ onExport }: { onExport: () => Promise<void> }) {
  const [pending, setPending] = useState(false)

  async function handleClick() {
    setPending(true)
    try {
      await onExport()
    } catch {
      toast.error("Falha ao exportar o relatorio")
    } finally {
      setPending(false)
    }
  }

  return (
    <Button type="button" variant="outline" size="sm" disabled={pending} onClick={handleClick}>
      {pending ? (
        <>
          <Loader2 size={15} strokeWidth={1.5} className="animate-spin" />
          Exportando...
        </>
      ) : (
        <>
          <Download size={15} strokeWidth={1.5} />
          Exportar CSV
        </>
      )}
    </Button>
  )
}
