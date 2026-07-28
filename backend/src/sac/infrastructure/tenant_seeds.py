from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.catalog import CatalogItem, CatalogKind
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository

DEFAULT_BRANDS: list[tuple[str, str | None]] = [("KODI", None), ("STALEKS", None)]

DEFAULT_DEFECT_TYPES: list[tuple[str, str | None]] = [
    ("Danificado", "Produto chegou danificado ou foi danificado no transporte."),
    ("Adaptacao/modelo errado", "Cliente solicita troca por outro modelo."),
    ("Nao recebeu", "Cliente nao recebeu o produto."),
    ("Sem afiacao/precisao", "Problema relacionado a falta de fio ou afiacao do produto."),
    ("Defeito de fabricacao", "Produto com defeito oriundo do processo de fabricacao."),
    ("Oxidacao", "Produto apresentou oxidacao."),
    ("Quebra da ferramenta", "Produto quebrou durante o uso."),
    ("Extraviado", "Produto extraviado no transporte."),
    ("Cancelado", "Reclamacao cancelada."),
    ("Arrependimento de compra", "Cliente deseja devolver o produto por arrependimento."),
    ("Produto divergente", "Produto recebido diferente do pedido."),
    ("Embalagem vazia", "Embalagem chegou sem o produto."),
    ("Mau uso", "Produto danificado por uso incorreto."),
    ("Fora do prazo", "Solicitacao fora do prazo de garantia."),
]

DEFAULT_SOLUTION_TYPES: list[tuple[str, str | None]] = [
    ("Troca pelo mesmo item", None),
    ("Troca por outro item", None),
    ("Envio de peca", None),
    ("Reembolso", None),
    ("50% off", None),
    ("100% off", None),
    ("Voucher", None),
    ("Desconto em nova compra", None),
    ("Orientado procurar marketplace/transportadora", None),
    ("Encaminhado para afiacao", None),
]

DEFAULT_PURCHASE_CHANNELS: list[tuple[str, str | None]] = [
    ("Site KODI", None),
    ("Site STALEKS", None),
    ("SAC", None),
    ("Beauty Show", None),
    ("Mercado Livre", None),
    ("Shopee", None),
    ("Revendedor", None),
]

CATALOG_DEFAULTS: dict[CatalogKind, list[tuple[str, str | None]]] = {
    CatalogKind.BRAND: DEFAULT_BRANDS,
    CatalogKind.DEFECT_TYPE: DEFAULT_DEFECT_TYPES,
    CatalogKind.SOLUTION_TYPE: DEFAULT_SOLUTION_TYPES,
    CatalogKind.PURCHASE_CHANNEL: DEFAULT_PURCHASE_CHANNELS,
}


async def seed_tenant_defaults(session: AsyncSession) -> int:
    created = 0
    for kind, defaults in CATALOG_DEFAULTS.items():
        repo = SqlCatalogRepository(session, kind)
        for name, description in defaults:
            if await repo.get_by_name(name) is None:
                await repo.add(CatalogItem(id=uuid4(), name=name, description=description))
                created += 1
    return created
