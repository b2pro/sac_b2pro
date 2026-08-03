from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import seed_user, token_for

DEFAULTS = {"theme": "sistema", "notify_toast": True, "notify_sound": False}


async def test_get_sem_linha_devolve_defaults_sem_gravar(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await seed_user(session, email="prefs1@teste.com")
    headers = token_for(user)

    res = await client.get("/api/preferencias", headers=headers)

    assert res.status_code == 200
    assert res.json() == DEFAULTS


async def test_put_grava_e_get_reflete(client: AsyncClient, session: AsyncSession) -> None:
    user = await seed_user(session, email="prefs2@teste.com")
    headers = token_for(user)

    res = await client.put(
        "/api/preferencias",
        json={"theme": "escuro", "notify_toast": False, "notify_sound": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == {"theme": "escuro", "notify_toast": False, "notify_sound": True}

    res = await client.get("/api/preferencias", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"theme": "escuro", "notify_toast": False, "notify_sound": True}


async def test_put_de_novo_atualiza_upsert(client: AsyncClient, session: AsyncSession) -> None:
    user = await seed_user(session, email="prefs3@teste.com")
    headers = token_for(user)

    res = await client.put(
        "/api/preferencias",
        json={"theme": "escuro", "notify_toast": False, "notify_sound": True},
        headers=headers,
    )
    assert res.status_code == 200

    res = await client.put(
        "/api/preferencias",
        json={"theme": "claro", "notify_toast": True, "notify_sound": False},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == {"theme": "claro", "notify_toast": True, "notify_sound": False}

    res = await client.get("/api/preferencias", headers=headers)
    assert res.json() == {"theme": "claro", "notify_toast": True, "notify_sound": False}


async def test_put_rejeita_tema_fora_dos_tres_valores(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await seed_user(session, email="prefs4@teste.com")
    headers = token_for(user)

    res = await client.put(
        "/api/preferencias",
        json={"theme": "roxo", "notify_toast": True, "notify_sound": False},
        headers=headers,
    )

    assert res.status_code == 422


async def test_sem_token_da_401(client: AsyncClient) -> None:
    res = await client.get("/api/preferencias")
    assert res.status_code == 401

    res = await client.put(
        "/api/preferencias",
        json={"theme": "claro", "notify_toast": True, "notify_sound": False},
    )
    assert res.status_code == 401


async def test_super_admin_sem_tenant_no_token_tem_preferencias(
    client: AsyncClient, session: AsyncSession
) -> None:
    # super_admin nao tem tenant ativo no token (nao passa por get_tenant_session),
    # entao o endpoint precisa funcionar so com get_current_identity.
    admin = await seed_user(session, email="admin-prefs@teste.com", is_super_admin=True)
    headers = token_for(admin)

    res = await client.get("/api/preferencias", headers=headers)
    assert res.status_code == 200
    assert res.json() == DEFAULTS

    res = await client.put(
        "/api/preferencias",
        json={"theme": "escuro", "notify_toast": True, "notify_sound": True},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == {"theme": "escuro", "notify_toast": True, "notify_sound": True}


async def test_user_id_vem_sempre_do_token_nunca_le_ou_grava_de_outro(
    client: AsyncClient, session: AsyncSession
) -> None:
    # seguranca: nao ha campo user_id no corpo/query do PUT nem do GET, entao
    # nao ha como B ler ou sobrescrever as preferencias de A so por conhecer o
    # id dele -- cada token so alcanca a propria linha.
    user_a = await seed_user(session, email="prefs-a@teste.com")
    user_b = await seed_user(session, email="prefs-b@teste.com")
    headers_a = token_for(user_a)
    headers_b = token_for(user_b)

    res = await client.put(
        "/api/preferencias",
        json={"theme": "escuro", "notify_toast": False, "notify_sound": True},
        headers=headers_a,
    )
    assert res.status_code == 200

    res = await client.get("/api/preferencias", headers=headers_b)
    assert res.status_code == 200
    assert res.json() == DEFAULTS
