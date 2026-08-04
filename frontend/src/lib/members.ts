import { api } from "@/lib/api"

export type MemberRole = "admin" | "supervisor" | "atendente" | "visualizador"

export type Member = {
  id: string
  name: string
  role: string
  active: boolean
}

/** Listagem enxuta (sem email) que qualquer papel autenticado alcanca: e o que
 *  alimenta os seletores de atribuicao de ticket e os filtros de relatorio. NAO
 *  apontar para `/membros/gerencia` — aquele endpoint exige GERENCIAR_USUARIOS e
 *  atendente e visualizador levariam 403 nos proprios seletores. */
export const listMembers = () => api<Member[]>("/membros")

export type MemberDetail = {
  id: string
  name: string
  email: string
  role: MemberRole
  /** Vinculo do usuario com ESTE tenant. Falso tira o acesso aqui e deixa o
   *  usuario intacto nos outros. */
  active: boolean
  /** Conta global do usuario. Falsa bloqueia o login em qualquer tenant e so o
   *  super admin da plataforma reverte — o admin do tenant nao alcanca. */
  user_active: boolean
}

export type MemberCreateInput = {
  email: string
  role: MemberRole
  name: string
  password: string
}

/** Listagem gerencial (com email e os dois estados). Exige GERENCIAR_USUARIOS,
 *  permissao que so o papel admin tem. */
export const listMembersAdmin = () => api<MemberDetail[]>("/membros/gerencia")

/** `name` e `password` sao OBRIGATORIOS, apesar de o schema da API declarar os
 *  dois como opcionais: o use case recusa a requisicao sem eles em todo fluxo,
 *  inclusive quando o email ja existe na plataforma e os dois vao ser
 *  descartados. A divergencia e deliberada — exigir no schema faria o 422
 *  disparar antes da checagem de permissao, e validar sempre e o que impede o
 *  endpoint de virar um oraculo de quais emails sao contas de verdade. */
export const createMember = (input: MemberCreateInput) =>
  api<MemberDetail>("/membros", { method: "POST", body: input })

export const updateMember = (userId: string, patch: { role?: MemberRole; active?: boolean }) =>
  api<MemberDetail>(`/membros/${userId}`, { method: "PATCH", body: patch })

export const resetMemberPassword = (userId: string, password: string) =>
  api<void>(`/membros/${userId}/senha`, { method: "POST", body: { password } })
