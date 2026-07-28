"""
Canal 🎮・registro — criado (ou reaproveitado, se já existir) na primeira
vez que o bot sobe, com a mensagem permanente contendo o botão
[🔗 Conectar Steam].

Chamado a partir de bot/events.py (on_ready), não de um comando — o
usuário não precisa fazer nada pra esse canal existir, ele já aparece
pronto assim que o bot entra/reinicia no servidor.
"""

from __future__ import annotations

import logging

import discord

from ui.views import SteamConnectView

logger = logging.getLogger(__name__)

CHANNEL_NAME = "🎮・registro"
EMBED_TITLE = "🎮 VINCULE SUA CONTA STEAM"
EMBED_DESCRIPTION = "Para acessar a loja DayZ é necessário vincular sua conta Steam."


async def ensure_register_channel(guild: discord.Guild) -> discord.TextChannel:
    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)

    if channel is None:
        channel = await guild.create_text_channel(CHANNEL_NAME)
        logger.info("Canal '%s' criado no servidor %s.", CHANNEL_NAME, guild.name)

    if not await _has_register_message(channel):
        await _post_register_message(channel)

    return channel


async def _has_register_message(channel: discord.TextChannel) -> bool:
    """Evita repostar a mensagem permanente a cada restart do bot —
    procura nas últimas mensagens do próprio bot por esse embed."""

    async for message in channel.history(limit=50):
        if message.author.id == channel.guild.me.id and message.embeds:
            if message.embeds[0].title == EMBED_TITLE:
                return True
    return False


async def _post_register_message(channel: discord.TextChannel) -> None:
    embed = discord.Embed(
        title=EMBED_TITLE,
        description=EMBED_DESCRIPTION,
        color=discord.Color.dark_blue(),
    )
    await channel.send(embed=embed, view=SteamConnectView())
    logger.info("Mensagem permanente de registro Steam postada em #%s.", channel.name)
