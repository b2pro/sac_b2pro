/** Props de acessibilidade pro controle (Input, SelectTrigger, Textarea) que o
 *  componente FieldError (components/ui/field-error.tsx) documenta:
 *  aria-invalid liga o estado visual (classes aria-invalid: dos componentes
 *  ui/*), aria-describedby liga a mensagem ao controle pro leitor de tela.
 *  Fica num arquivo .ts em vez de dentro do componente porque misturar
 *  export de componente e de funcao no mesmo .tsx aciona o aviso do
 *  react-refresh/only-export-components. */
export function fieldErrorProps(fieldId: string, message: string | null) {
  return {
    "aria-invalid": message != null,
    "aria-describedby": message != null ? `${fieldId}-error` : undefined,
  } as const
}
