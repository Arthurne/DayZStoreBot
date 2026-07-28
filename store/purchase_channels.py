"""
Canal privado de atendimento — um canal por pedido, visível só pro
comprador e pra administradores. Criado automaticamente quando a compra é
confirmada (PENDENTE), pra centralizar comprovante de PIX, dúvidas etc.
num lugar só, em vez de tudo acontecer em DM ou espalhado pelo servidor.
"""

from __future__ import annotations

import logging

import discord

from database.models import Product, Purchase

logger = logging.getLogger(__name__)

CATEGORY_NAME = "🎫 ATENDIMENTO"


async def ensure_purchase_channel(
    *, purchase: Purchase, product: Product, member: discord.Member
) -> discord.TextChannel | None:
    guild = member.guild

    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if category is None:
        try:
            category = await guild.create_category(CATEGORY_NAME)
        except discord.Forbidden:
            logger.warning("Sem permissão para criar a categoria '%s' — canal de atendimento não criado.", CATEGORY_NAME)
            return None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel_name = f"pedido-{purchase.id}"
    try:
        channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
    except discord.Forbidden:
        logger.warning("Sem permissão para criar o canal de atendimento do pedido #%s.", purchase.id)
        return None

    embed = discord.Embed(
        title=f"🎫 Pedido #{purchase.id}",
        description=(
            f"**Produto:** {product.name}\n"
            f"**Valor:** R${float(purchase.price):.2f}\n"
            f"**Status:** {purchase.status.value}\n\n"
            f"Um administrador vai confirmar o pagamento por aqui em breve."
        ),
        color=discord.Color.blurple(),
    )

    from ui.views import PurchaseApprovalView

    await channel.send(content=member.mention, embed=embed, view=PurchaseApprovalView(purchase.id))

    logger.info("Canal de atendimento criado para o pedido #%s: #%s", purchase.id, channel.name)
    return channel
