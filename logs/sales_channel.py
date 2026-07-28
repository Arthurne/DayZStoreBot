"""
Canal 📜・logs-vendas — histórico (visível pra quem tiver acesso ao canal)
de tudo que acontece com pedidos: nova compra, pagamento confirmado,
entrega, cancelamento. Complementa o logger.info() da aplicação, não
substitui — se o bot cair, o log em arquivo/console continua existindo
mesmo sem o Discord.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

CHANNEL_NAME = "📜・logs-vendas"


async def ensure_sales_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is not None:
        return channel

    try:
        channel = await guild.create_text_channel(CHANNEL_NAME)
        logger.info("Canal '%s' criado no servidor %s.", CHANNEL_NAME, guild.name)
        return channel
    except discord.Forbidden:
        logger.warning("Sem permissão para criar o canal '%s'.", CHANNEL_NAME)
        return None


async def log_purchase_event(bot: commands.Bot, *, title: str, description: str, color: discord.Color) -> None:
    from config import settings

    guild = bot.get_guild(settings.guild_id)
    if guild is None:
        return

    channel = await ensure_sales_log_channel(guild)
    if channel is None:
        return

    embed = discord.Embed(title=title, description=description, color=color)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        logger.warning("Falha ao postar log de venda em #%s.", CHANNEL_NAME)
