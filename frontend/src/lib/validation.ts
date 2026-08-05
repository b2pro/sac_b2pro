/** Minimo de senha compartilhado pelos formularios que cadastram ou redefinem
 *  senha (membros do tenant e usuarios da plataforma) — nao hardcodear 8 em
 *  cada tela. */
export const MIN_PASSWORD_LENGTH = 8

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Substitui a checagem nativa de type="email", desligada por noValidate no
 *  form: formato simples (usuario@dominio.algo), o suficiente pro aviso
 *  inline. Validar se o email de fato existe/recebe e responsabilidade do
 *  backend. */
export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value)
}
