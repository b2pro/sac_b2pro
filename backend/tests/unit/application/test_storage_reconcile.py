from datetime import UTC, datetime, timedelta

from sac.application.use_cases.storage_reconcile import ReconcileOrphansUseCase
from sac.domain.errors import StorageUnavailableError
from tests.unit.fakes_attachments import FakeStorage

AGORA = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class FakeKnownKeys:
    def __init__(self, keys: set[str] | None = None, erro: Exception | None = None) -> None:
        self._keys = keys or set()
        self._erro = erro
        self.chamadas = 0

    async def known_keys(self) -> set[str]:
        self.chamadas += 1
        if self._erro is not None:
            raise self._erro
        return set(self._keys)


def _com_objeto(storage: FakeStorage, key: str, idade_horas: float) -> None:
    storage.simulate_upload(key, b"conteudo", "image/png")
    storage.last_modified[key] = AGORA - timedelta(hours=idade_horas)


async def test_orfao_velho_e_apagado_e_outro_tenant_nao_e_tocado() -> None:
    """O orfao sem linha no banco e mais velho que a margem e apagado. O objeto
    de OUTRO tenant, igualmente orfao e velho, nao pode ser tocado: a varredura
    e por prefixo de tenant, e o prefixo tem que chegar de verdade ao storage."""
    storage = FakeStorage()
    _com_objeto(storage, "acme/upload-perdido/x.png", idade_horas=48)
    _com_objeto(storage, "outro/upload-perdido/y.png", idade_horas=48)

    total = await ReconcileOrphansUseCase(
        storage=storage,
        known_keys=FakeKnownKeys(),
        prefix="acme/",
        older_than_hours=24,
    ).execute(AGORA)

    assert total == 1
    assert storage.deleted == ["acme/upload-perdido/x.png"]
    assert storage.head("outro/upload-perdido/y.png") is not None


async def test_orfao_recente_sobrevive_inclusive_na_fronteira() -> None:
    """A margem de idade existe para o upload EM VOO: o objeto ja esta no bucket
    e a linha ainda nao foi gravada. Um orfao com menos de 24h nunca pode ser
    apagado - e na fronteira exata (idade == 24h) tambem nao, porque a regra e
    last_modified estritamente menor que o limite."""
    storage = FakeStorage()
    _com_objeto(storage, "acme/em-voo/recente.png", idade_horas=1)
    _com_objeto(storage, "acme/em-voo/fronteira.png", idade_horas=24)

    total = await ReconcileOrphansUseCase(
        storage=storage,
        known_keys=FakeKnownKeys(),
        prefix="acme/",
        older_than_hours=24,
    ).execute(AGORA)

    assert total == 0
    assert storage.deleted == []
    assert storage.head("acme/em-voo/recente.png") is not None
    assert storage.head("acme/em-voo/fronteira.png") is not None


async def test_chave_conhecida_nunca_e_apagada_por_mais_velha_que_seja() -> None:
    """Anexo ativo (original + as duas previews) e foto de produto: todas as
    chaves conhecidas ficam, mesmo com anos de idade. O orfao no meio delas e o
    unico que sai."""
    storage = FakeStorage()
    conhecidas = {
        "acme/11111111-1111-1111-1111-111111111111/aaaa.png",
        "acme/11111111-1111-1111-1111-111111111111/previews/aaaa.webp",
        "acme/11111111-1111-1111-1111-111111111111/previews/aaaa_medium.webp",
        "acme/catalogo/produtos/22222222-2222-2222-2222-222222222222/bbbb.png",
        "acme/catalogo/produtos/22222222-2222-2222-2222-222222222222/previews/bbbb.webp",
    }
    for chave in conhecidas:
        _com_objeto(storage, chave, idade_horas=24 * 365)
    _com_objeto(storage, "acme/lixo/solto.png", idade_horas=24 * 365)

    total = await ReconcileOrphansUseCase(
        storage=storage,
        known_keys=FakeKnownKeys(conhecidas),
        prefix="acme/",
        older_than_hours=24,
    ).execute(AGORA)

    assert total == 1
    assert storage.deleted == ["acme/lixo/solto.png"]
    for chave in conhecidas:
        assert storage.head(chave) is not None


async def test_falha_ao_apagar_um_objeto_nao_impede_os_demais() -> None:
    storage = FakeStorage()
    for nome in ("a", "b", "c"):
        _com_objeto(storage, f"acme/orfaos/{nome}.png", idade_horas=48)
    storage.fail_delete_for = {"acme/orfaos/b.png"}

    total = await ReconcileOrphansUseCase(
        storage=storage,
        known_keys=FakeKnownKeys(),
        prefix="acme/",
        older_than_hours=24,
    ).execute(AGORA)

    assert total == 2
    assert storage.deleted == ["acme/orfaos/a.png", "acme/orfaos/c.png"]
    assert storage.head("acme/orfaos/b.png") is not None


async def test_falha_ao_ler_as_chaves_conhecidas_nao_apaga_nada() -> None:
    """Propriedade critica: sem a lista de chaves conhecidas nao existe decisao
    possivel sobre o que e orfao. A falha do banco tem que subir ANTES de
    qualquer delete - tratar a leitura falha como "nenhuma chave conhecida"
    apagaria o bucket inteiro do tenant."""
    storage = FakeStorage()
    _com_objeto(storage, "acme/anexo/legitimo.png", idade_horas=48)

    try:
        await ReconcileOrphansUseCase(
            storage=storage,
            known_keys=FakeKnownKeys(erro=RuntimeError("banco indisponivel")),
            prefix="acme/",
            older_than_hours=24,
        ).execute(AGORA)
    except RuntimeError as exc:
        assert "banco indisponivel" in str(exc)
    else:
        raise AssertionError("a falha de leitura do banco tinha que propagar")

    assert storage.deleted == []
    assert storage.head("acme/anexo/legitimo.png") is not None


async def test_falha_ao_listar_o_bucket_propaga_sem_apagar() -> None:
    class ListaQuebrada(FakeStorage):
        def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
            raise StorageUnavailableError("storage indisponível")

    storage = ListaQuebrada()

    try:
        await ReconcileOrphansUseCase(
            storage=storage,
            known_keys=FakeKnownKeys(),
            prefix="acme/",
            older_than_hours=24,
        ).execute(AGORA)
    except StorageUnavailableError:
        pass
    else:
        raise AssertionError("a falha de listagem tinha que propagar")

    assert storage.deleted == []
