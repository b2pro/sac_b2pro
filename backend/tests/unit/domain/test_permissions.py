from sac.domain.permissions import ROLE_PERMISSIONS, Permission, Role, has_permission


def test_admin_tem_todas_as_permissoes() -> None:
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)


def test_supervisor_nao_gerencia_usuarios() -> None:
    assert not has_permission(Role.SUPERVISOR, Permission.GERENCIAR_USUARIOS)
    assert has_permission(Role.SUPERVISOR, Permission.DECIDIR_TICKET)


def test_atendente_nao_decide_nem_gerencia_cadastros() -> None:
    assert not has_permission(Role.ATENDENTE, Permission.DECIDIR_TICKET)
    assert not has_permission(Role.ATENDENTE, Permission.GERENCIAR_CADASTROS)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_TICKET)
    assert has_permission(Role.ATENDENTE, Permission.ENVIAR_PARA_ANALISE)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_LISTAR_CADASTROS)
    assert has_permission(Role.ATENDENTE, Permission.LISTAR_CADASTROS)


def test_visualizador_so_leitura() -> None:
    assert ROLE_PERMISSIONS[Role.VISUALIZADOR] == frozenset(
        {Permission.VER_TODOS_TICKETS, Permission.LISTAR_CADASTROS, Permission.VER_VISIBILIDADE}
    )
