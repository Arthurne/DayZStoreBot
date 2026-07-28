"""
Canal 📦・entregas — mensagem fixa com o botão "Minhas Entregas". O jogador
nunca digita comando: clica, e vê (efêmero, só ele) a lista das PRÓPRIAS
entregas, puxada pelo SteamID vinculado à conta dele.
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)

CHANNEL_NAME = "📦・entregas"


async def ensure_deliveries_channel(guild: discord.Guild) -> discord.TextChannel | None:
    from ui.views import MyDeliveriesView

    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is not None:
        return channel

    try:
        channel = await guild.create_text_channel(CHANNEL_NAME)
    except discord.Forbidden:
        logger.warning("Sem permissão para criar o canal '%s'.", CHANNEL_NAME)
        return None

    embed = discord.Embed(
        title="📦 SUAS ENTREGAS",
        description="Clique no botão abaixo para ver o status das suas compras.",
        color=discord.Color.blurple(),
    )
    await channel.send(embed=embed, view=MyDeliveriesView())
    logger.info("Canal '%s' criado no servidor %s.", CHANNEL_NAME, guild.name)
    return channel
