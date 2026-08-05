import { cn } from "@/lib/utils"

/** Mensagem de erro inline de um campo: substitui a bolha nativa do browser e o
 *  toast (reservado a erro que nao pertence a um campo especifico). Sempre ao
 *  lado de aria-invalid no controle — usar fieldErrorProps() (lib/field-error)
 *  nos dois lados pra nao desalinhar o id. */
function FieldError({
  fieldId,
  message,
  className,
}: {
  fieldId: string
  message: string | null
  className?: string
}) {
  if (!message) return null
  return (
    <p id={`${fieldId}-error`} className={cn("text-xs text-destructive", className)}>
      {message}
    </p>
  )
}

export { FieldError }
