from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    ATENDENTE = "atendente"
    VISUALIZADOR = "visualizador"


class Permission(StrEnum):
    VER_TODOS_TICKETS = "ver_todos_tickets"
    VER_PROPRIOS_TICKETS = "ver_proprios_tickets"
    CRIAR_TICKET = "criar_ticket"
    EDITAR_QUALQUER_TICKET = "editar_qualquer_ticket"
    EDITAR_PROPRIO_TICKET = "editar_proprio_ticket"
    ENVIAR_PARA_ANALISE = "enviar_para_analise"
    DECIDIR_TICKET = "decidir_ticket"
    OPERAR_LOGISTICA_TODOS = "operar_logistica_todos"
    OPERAR_LOGISTICA_PROPRIOS = "operar_logistica_proprios"
    COMENTAR_ANEXAR = "comentar_anexar"
    GERENCIAR_CADASTROS = "gerenciar_cadastros"
    CRIAR_LISTAR_CADASTROS = "criar_listar_cadastros"
    LISTAR_CADASTROS = "listar_cadastros"
    GERENCIAR_USUARIOS = "gerenciar_usuarios"
    VER_VISIBILIDADE = "ver_visibilidade"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.SUPERVISOR: frozenset(Permission) - {Permission.GERENCIAR_USUARIOS},
    Role.ATENDENTE: frozenset(
        {
            Permission.VER_PROPRIOS_TICKETS,
            Permission.CRIAR_TICKET,
            Permission.EDITAR_PROPRIO_TICKET,
            Permission.ENVIAR_PARA_ANALISE,
            Permission.OPERAR_LOGISTICA_PROPRIOS,
            Permission.COMENTAR_ANEXAR,
            Permission.CRIAR_LISTAR_CADASTROS,
            Permission.LISTAR_CADASTROS,
            Permission.VER_VISIBILIDADE,
        }
    ),
    Role.VISUALIZADOR: frozenset(
        {
            Permission.VER_TODOS_TICKETS,
            Permission.LISTAR_CADASTROS,
            Permission.VER_VISIBILIDADE,
        }
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
