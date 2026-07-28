"""
Fila de entregas. Sem nada de Discord aqui — quem chama isso (comandos,
botões) é que cuida de canal/embed/notificação.

Fluxo:
    Purchase PAGO --[automático, ver store/purchases.approve_payment]--> Delivery criada (Pendente)
    Pendente --[admin: Processar]--> Processando
    Processando --[admin: Marcar como entregue]--> Entregue (+ Purchase também vira ENTREGUE)
    Pendente/Processando --[admin: Marcar como falhou]--> Falhou (com motivo opcional)

Nenhuma integração real (RCON/API/Mod/Webhook) é acionada por essas
funções ainda — isso é o gancho que delivery/providers.py deixa pronto pra
uma etapa futura.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database.database import get_session
from database.models import Delivery, DeliveryStatus, Product, Purchase

logger = logging.getLogger(__name__)


async def create_delivery_for_purchase(purchase_id: int) -> Delivery | None:
    """Chamada automaticamente assim que um pedido é aprovado (PAGO) — ver
    store/purchases.approve_payment(). Não deveria ser chamada diretamente
    por um comando/botão."""

    async with get_session() as session:
        existing = await session.execute(select(Delivery).where(Delivery.purchase_id == purchase_id))
        existing_delivery = existing.scalar_one_or_none()
        if existing_delivery:
            logger.warning("Pedido #%s já tem entrega criada — ignorando duplicata.", purchase_id)
            return existing_delivery

        purchase = await session.get(Purchase, purchase_id)
        if purchase is None:
            return None
        product = await session.get(Product, purchase.product_id)

        delivery = Delivery(
            purchase_id=purchase_id,
            steam_id=purchase.steam_id,
            product=product.name if product else "Produto removido",
            items=list(product.items) if product else [],
            status=DeliveryStatus.pendente,
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)

    logger.info("Entrega #%s criada para o pedido #%s (steam_id=%s).", delivery.id, purchase_id, delivery.steam_id)
    return delivery


async def get_delivery_by_id(delivery_id: int) -> Delivery | None:
    async with get_session() as session:
        return await session.get(Delivery, delivery_id)


async def list_deliveries(status: DeliveryStatus | None = None) -> list[Delivery]:
    async with get_session() as session:
        query = select(Delivery).order_by(Delivery.created_at.desc())
        if status is not None:
            query = query.where(Delivery.status == status)
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_deliveries_for_steam_id(steam_id: str) -> list[Delivery]:
    async with get_session() as session:
        result = await session.execute(
            select(Delivery).where(Delivery.steam_id == steam_id).order_by(Delivery.created_at.desc())
        )
        return list(result.scalars().all())


async def set_processing(delivery_id: int, *, admin_discord_id: int) -> Delivery | None:
    async with get_session() as session:
        delivery = await session.get(Delivery, delivery_id)
        if delivery is None:
            return None
        delivery.status = DeliveryStatus.processando
        delivery.processed_by = admin_discord_id
        await session.commit()
        await session.refresh(delivery)

    logger.info("Entrega #%s marcada como Processando por discord_id=%s.", delivery_id, admin_discord_id)
    return delivery


async def set_delivered(delivery_id: int, *, admin_discord_id: int) -> Delivery | None:
    from store.purchases import mark_delivered

    async with get_session() as session:
        delivery = await session.get(Delivery, delivery_id)
        if delivery is None:
            return None
        delivery.status = DeliveryStatus.entregue
        delivery.processed_by = admin_discord_id
        delivery.delivered_at = datetime.now(timezone.utc)
        purchase_id = delivery.purchase_id
        await session.commit()
        await session.refresh(delivery)

    await mark_delivered(purchase_id)  # espelha o status também no Purchase

    logger.info("Entrega #%s marcada como Entregue por discord_id=%s.", delivery_id, admin_discord_id)
    return delivery


async def set_failed(delivery_id: int, *, admin_discord_id: int, reason: str | None) -> Delivery | None:
    async with get_session() as session:
        delivery = await session.get(Delivery, delivery_id)
        if delivery is None:
            return None
        delivery.status = DeliveryStatus.falhou
        delivery.processed_by = admin_discord_id
        delivery.error_message = reason
        await session.commit()
        await session.refresh(delivery)

    logger.info("Entrega #%s marcada como Falhou por discord_id=%s (motivo: %s).", delivery_id, admin_discord_id, reason)
    return delivery


STATUS_EMOJI = {
    DeliveryStatus.pendente: "⚪",
    DeliveryStatus.processando: "🟡",
    DeliveryStatus.entregue: "✅",
    DeliveryStatus.falhou: "❌",
}
