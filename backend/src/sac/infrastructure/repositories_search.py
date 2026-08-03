"""Repositorio SQL da busca global (Task 7 da Fase 4).

Tres selects independentes -- tickets, clientes, produtos --, cada um
limitado a `limit` linhas. Os indices GIN de trigrama que sustentam o
`ilike '%termo%'` sao criados em 0008_indices_busca (nome/order_code) e
0010_indices_busca_global (documento/telefone/email/sku).
"""

from uuid import UUID

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.use_cases.global_search import (
    CustomerHit,
    GlobalSearchResult,
    ProductHit,
    TicketHit,
)
from sac.domain.documents import normalize_digits
from sac.domain.tickets import TicketStatus
from sac.infrastructure.models_tenant import BrandModel, CustomerModel, ProductModel, TicketModel
from sac.infrastructure.sql_search import LIKE_ESCAPE_CHAR, escape_like


class SqlGlobalSearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, term: str, owner_user_id: UUID | None, limit: int) -> GlobalSearchResult:
        escaped = escape_like(term)
        digits = normalize_digits(term)

        return GlobalSearchResult(
            tickets=await self._search_tickets(term, escaped, owner_user_id, limit),
            customers=await self._search_customers(escaped, digits, limit),
            products=await self._search_products(escaped, limit),
        )

    async def _search_tickets(
        self, term: str, escaped: str, owner_user_id: UUID | None, limit: int
    ) -> list[TicketHit]:
        # numero de ticket casa por prefixo quando o termo (sem "#", como o
        # usuario ve na UI) e so digitos -- mesma abordagem da busca livre em
        # SqlTicketRepository._base_stmt (repositories_tickets.py).
        number_term = term.lstrip("#")
        conditions = [TicketModel.order_code.ilike(f"%{escaped}%", escape=LIKE_ESCAPE_CHAR)]
        if number_term.isdigit():
            conditions.append(cast(TicketModel.number, String).like(f"{escape_like(number_term)}%"))

        stmt = (
            select(TicketModel, CustomerModel.name, BrandModel.name)
            .outerjoin(CustomerModel, TicketModel.customer_id == CustomerModel.id)
            .outerjoin(BrandModel, TicketModel.brand_id == BrandModel.id)
            .where(TicketModel.deleted_at.is_(None), or_(*conditions))
        )
        if owner_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == owner_user_id)
        stmt = stmt.order_by(TicketModel.opened_at.desc()).limit(limit)

        rows = (await self._session.execute(stmt)).all()
        return [
            TicketHit(
                id=ticket.id,
                number=ticket.number,
                status=TicketStatus(ticket.status),
                customer_name=customer_name,
                brand_name=brand_name,
            )
            for ticket, customer_name, brand_name in rows
        ]

    async def _search_customers(self, escaped: str, digits: str, limit: int) -> list[CustomerHit]:
        # nome/email usam o termo original (escapado); documento/telefone
        # casam so pelos digitos, e ficam de fora quando o termo nao tem
        # nenhum (senao "%%" combinaria com qualquer linha).
        conditions = [
            CustomerModel.name.ilike(f"%{escaped}%", escape=LIKE_ESCAPE_CHAR),
            CustomerModel.email.ilike(f"%{escaped}%", escape=LIKE_ESCAPE_CHAR),
        ]
        if digits:
            escaped_digits = escape_like(digits)
            conditions.append(
                CustomerModel.document.like(f"%{escaped_digits}%", escape=LIKE_ESCAPE_CHAR)
            )
            conditions.append(
                CustomerModel.phone.like(f"%{escaped_digits}%", escape=LIKE_ESCAPE_CHAR)
            )

        stmt = (
            select(CustomerModel)
            .where(CustomerModel.deleted_at.is_(None), or_(*conditions))
            .order_by(CustomerModel.name)
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [CustomerHit(id=c.id, name=c.name, document=c.document) for c in rows]

    async def _search_products(self, escaped: str, limit: int) -> list[ProductHit]:
        conditions = [
            ProductModel.name.ilike(f"%{escaped}%", escape=LIKE_ESCAPE_CHAR),
            ProductModel.sku.ilike(f"%{escaped}%", escape=LIKE_ESCAPE_CHAR),
        ]
        stmt = (
            select(ProductModel)
            .where(ProductModel.deleted_at.is_(None), or_(*conditions))
            .order_by(ProductModel.name)
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [ProductHit(id=p.id, name=p.name, sku=p.sku) for p in rows]
