import { api } from "@/lib/api"

export type Member = {
  id: string
  name: string
  role: string
  active: boolean
}

export const listMembers = () => api<Member[]>("/membros")
