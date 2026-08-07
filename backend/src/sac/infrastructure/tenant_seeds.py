from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sac.infrastructure.models_tenant import SlaPolicyModel

# Nenhum catalogo e semeado. Marca, tipo de defeito, tipo de solucao e canal de
# compra descrevem a operacao de quem contratou -- KODI, STALEKS, os defeitos de
# ferramenta e as lojas proprias vieram do primeiro cliente e nao valem como
# padrao. O tenant nasce com os quatro catalogos vazios, prontos para o setup de
# quem for opera-lo. Tenant ja criado mantem o que tem: este seed so decide o que
# entra na criacao.
#
# A politica de SLA continua: nao cita marca nenhuma, so traduz a prioridade em
# horas, e um tenant sem ela nao consegue calcular prazo de ticket.
DEFAULT_SLA_POLICIES_ROWS: list[tuple[str, int, int]] = [
    ("urgente", 24, 12),
    ("alta", 48, 12),
    ("media", 72, 12),
    ("baixa", 120, 12),
]


async def seed_tenant_defaults(session: AsyncSession) -> int:
    created = 0

    existing_priorities = set((await session.scalars(select(SlaPolicyModel.priority))).all())
    for priority, hours, warn_hours in DEFAULT_SLA_POLICIES_ROWS:
        if priority in existing_priorities:
            continue
        session.add(
            SlaPolicyModel(id=uuid4(), priority=priority, hours=hours, warn_hours=warn_hours)
        )
        created += 1

    return created
