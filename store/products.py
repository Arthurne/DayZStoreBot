"""
Regras de negócio de produto (CRUD + ativação). Não sabe nada de Discord —
recebe/devolve dados simples e objetos ORM. Quem cria canal, posta embed
etc. é store/shop_channels.py, chamado por commands/products.py depois de
qualquer uma dessas funções.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from database.database import get_session
from database.models import Product

logger = logging.getLogger(__name__)


async def create_product(
    *, name: str, description: str, price: float, category: str, items: list[str], image_url: str | None
) -> Product:
    async with get_session() as session:
        product = Product(
            name=name,
            description=description,
            price=price,
            category=category,
            items=items,
            image_url=image_url,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

    logger.info("Produto criado: '%s' (id=%s, categoria=%s, preço=%.2f)", name, product.id, category, price)
    return product


async def update_product(
    product_id: int, *, name: str, description: str, price: float, category: str, items: list[str], image_url: str | None
) -> Product | None:
    async with get_session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            return None

        product.name = name
        product.description = description
        product.price = price
        product.category = category
        product.items = items
        product.image_url = image_url

        await session.commit()
        await session.refresh(product)

    logger.info("Produto atualizado: '%s' (id=%s)", name, product_id)
    return product


async def get_product_by_name(name: str) -> Product | None:
    async with get_session() as session:
        result = await session.execute(select(Product).where(Product.name.ilike(name)))
        return result.scalar_one_or_none()


async def get_product_by_id(product_id: int) -> Product | None:
    async with get_session() as session:
        return await session.get(Product, product_id)


async def list_products() -> list[Product]:
    async with get_session() as session:
        result = await session.execute(select(Product).order_by(Product.category, Product.name))
        return list(result.scalars().all())


async def set_active(product_id: int, active: bool) -> Product | None:
    async with get_session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            return None
        product.is_active = active
        await session.commit()
        await session.refresh(product)

    logger.info("Produto %s: '%s' (id=%s)", "ativado" if active else "desativado", product.name, product_id)
    return product


async def delete_product(product_id: int) -> Product | None:
    """Retorna o produto (já removido da sessão) pra quem chamou ainda
    conseguir ler channel_id/message_id e apagar a mensagem no Discord."""

    async with get_session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            return None

        # guarda uma cópia "desanexada" antes de deletar, pra ainda ter os
        # dados (channel_id/message_id) depois do commit
        snapshot = Product(
            id=product.id,
            name=product.name,
            category=product.category,
            channel_id=product.channel_id,
            message_id=product.message_id,
        )

        await session.delete(product)
        await session.commit()

    logger.info("Produto removido: '%s' (id=%s)", snapshot.name, product_id)
    return snapshot
