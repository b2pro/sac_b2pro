from sac.domain.permissions import Permission, Role, has_permission


def test_todos_os_papeis_tem_ver_visibilidade() -> None:
    for role in Role:
        assert has_permission(role, Permission.VER_VISIBILIDADE)
