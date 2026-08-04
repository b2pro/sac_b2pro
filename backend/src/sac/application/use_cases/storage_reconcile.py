import logging
from datetime import datetime, timedelta

from sac.application.ports_attachments import KnownKeysPort, StoragePort
from sac.domain.errors import StorageUnavailableError

logger = logging.getLogger(__name__)


class ReconcileOrphansUseCase:
    """Apaga do bucket os objetos que nenhuma linha do banco reconhece mais.

    E a rede de seguranca da delecao direta (expirar, descartar, excluir), que e
    best-effort, e o unico caminho que alcanca o upload que ganhou URL assinada
    e nunca virou linha - esse nao aparece em varredura nenhuma do banco.

    Duas travas protegem anexo vivo, e as duas sao essenciais:

    1. A margem de idade. Um upload EM VOO ja tem objeto no bucket e ainda nao
       tem linha; apagar so por "nao tem linha" destruiria o arquivo que o
       usuario esta enviando naquele instante. Por isso so entra na conta o
       objeto mais velho que `older_than_hours` (24h em producao). Nunca
       enfraquecer essa margem fora de teste.
    2. A lista de chaves conhecidas vem do banco e a falha ao le-la propaga.
       Tratar "nao consegui ler" como "nada e conhecido" apagaria o bucket
       inteiro do tenant.

    A listagem do bucket acontece ANTES da leitura do banco de proposito: assim
    o instantaneo do banco e o mais novo dos dois e cobre qualquer linha
    gravada durante a listagem, que de outra forma seria vista como orfa (a
    margem de idade tambem cobriria esse caso, mas as duas travas nao precisam
    depender uma da outra).
    """

    def __init__(
        self,
        storage: StoragePort,
        known_keys: KnownKeysPort,
        prefix: str,
        older_than_hours: int = 24,
    ) -> None:
        self._storage = storage
        self._known_keys = known_keys
        self._prefix = prefix
        self._older_than_hours = older_than_hours

    async def execute(self, now: datetime) -> int:
        objetos = self._storage.list_keys(self._prefix)
        conhecidas = await self._known_keys.known_keys()
        limite = now - timedelta(hours=self._older_than_hours)
        total = 0
        for key, last_modified in objetos:
            if key in conhecidas or last_modified >= limite:
                continue
            try:
                self._storage.delete(key)
            except StorageUnavailableError:
                # falha em UMA chave nao pode interromper a varredura: o que
                # sobrar orfao volta a ser candidato na proxima passada.
                logger.warning("falha ao apagar objeto orfao key=%s", key)
                continue
            total += 1
            logger.info("objeto orfao apagado key=%s", key)
        return total
