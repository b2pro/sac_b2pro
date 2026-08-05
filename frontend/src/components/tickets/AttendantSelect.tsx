import { useQuery } from "@tanstack/react-query"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { listMembers, type Member } from "@/lib/members"

const CARREGANDO = "__carregando"

function labelFor(member: Member): string {
  // Mesma regra do SupervisorSelect: um atendente inativo continua rotulado
  // como tal, nunca some silenciosamente da lista quando ele e o valor ja
  // atribuido (ver options abaixo).
  const papel = member.active ? member.role : `${member.role}, inativo`
  return `${member.name} (${papel})`
}

/** Seletor de atendente responsavel do ticket, usado so no dialog de editar
 *  dados: reatribuir exige EDITAR_QUALQUER_TICKET no backend, entao quem
 *  chega ate este campo ja e admin ou supervisor (ver `canDecide` em
 *  `lib/tickets`). Nunca oferece "nenhum" -- enviar attendant_user_id nulo e
 *  um no-op no backend, nao uma remocao de atribuicao, e todo ticket sempre
 *  tem um atendente. */
export function AttendantSelect({
  id,
  value,
  currentName,
  onChange,
}: {
  id: string
  value: string
  /** Nome do atendente atual do ticket (`TicketDetail.attendant_name`),
   *  conhecido sem depender da query de membros. Usado so no estado
   *  degradado abaixo -- fora dele a lista carregada e a fonte da verdade. */
  currentName: string | null
  onChange: (value: string) => void
}) {
  const { data: members, isError } = useQuery({
    queryKey: ["membros"],
    queryFn: listMembers,
    retry: false,
  })

  // Estado degradado: a query ainda nao resolveu ou falhou (sem retry, ver
  // acima). Sem isto o trigger ficaria em branco e o dropdown vazio -- sem
  // nem o atendente atual como opcao -- e nada avisaria o admin/supervisor
  // que a lista nao carregou. `currentName` vem de fora (o proprio detalhe
  // do ticket), entao o atendente atual sempre aparece, mesmo aqui: e o
  // valor que o campo ja tem, nao um sentinel nulo, e selecionar essa linha
  // e um no-op no backend (mesma regra do resto do componente).
  if (members === undefined) {
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue>{currentName ?? "Atendente atual"}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={value}>{currentName ?? "Atendente atual"}</SelectItem>
          <SelectItem value={CARREGANDO} disabled>
            {isError
              ? "Nao foi possivel carregar a lista de atendentes"
              : "Carregando lista de atendentes..."}
          </SelectItem>
        </SelectContent>
      </Select>
    )
  }

  const elegiveis = members.filter(
    (member) =>
      member.active &&
      (member.role === "admin" || member.role === "supervisor" || member.role === "atendente"),
  )

  // O atendente atual pode ter ficado inativo, ou trocado de papel, depois da
  // atribuicao. Ele nao entra no filtro acima, mas precisa continuar
  // aparecendo como opcao -- senao abrir e fechar o select sem tocar nele
  // trocaria o atendente do ticket por engano.
  const atualForaDaLista = members.find((m) => m.id === value)
  const jaListado = elegiveis.some((m) => m.id === value)
  const atendentes = atualForaDaLista && !jaListado ? [...elegiveis, atualForaDaLista] : elegiveis

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {atendentes.map((member) => (
          <SelectItem key={member.id} value={member.id}>
            {labelFor(member)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
