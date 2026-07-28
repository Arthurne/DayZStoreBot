"""
Eventos globais do bot.

on_ready fica aqui (e não em main.py) pra manter main.py só como o
"orquestrador" (cria o bot, carrega cogs, conecta no banco, dá start) —
qualquer lógica de evento cresce aqui dentro sem inchar o entrypoint.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.permissions import handle_permission_error, is_authorized_guild
from config import settings
from delivery.deliveries_channel import ensure_deliveries_channel
from logs.sales_channel import ensure_sales_log_channel
from steam.register_channel import ensure_register_channel

logger = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(
            "Bot conectado como %s (id=%s) — %d servidor(es), %d comando(s) sincronizado(s) localmente.",
            self.bot.user,
            self.bot.user.id if self.bot.user else "?",
            len(self.bot.guilds),
            len(self.bot.tree.get_commands()),
        )

        # Sanity check no boot: se por algum motivo o bot já estiver em algum
        # servidor não autorizado (ex: GUILD_ID mudou no .env depois de já
        # estar instalado em outro lugar), avisa e sai.
        for g in self.bot.guilds:
            if not is_authorized_guild(g.id):
                await self._leave_unauthorized_guild(g)

        guild = self.bot.get_guild(settings.guild_id)
        if guild is None:
            logger.error(
                "GUILD_ID=%s não corresponde a nenhum servidor onde o bot está. "
                "Canal de registro Steam não pôde ser criado/verificado.",
                settings.guild_id,
            )
            return

        if settings.steam_enabled:
            try:
                await ensure_register_channel(guild)
            except discord.Forbidden:
                logger.error(
                    "Sem permissão para criar/ler o canal '🎮・registro' no servidor %s. "
                    "Verifique as permissões do bot (Gerenciar Canais, Ver Canal, Enviar Mensagens).",
                    guild.name,
                )
        else:
            logger.info(
                "Steam desabilitada (%s). Canal '🎮・registro' não será criado — "
                "o restante do bot continua funcionando normalmente.",
                settings.steam_disabled_reason,
            )

        try:
            await ensure_deliveries_channel(guild)
        except discord.Forbidden:
            logger.error(
                "Sem permissão para criar/ler o canal '📦・entregas' no servidor %s.",
                guild.name,
            )

        try:
            await ensure_sales_log_channel(guild)
        except discord.Forbidden:
            logger.error(
                "Sem permissão para criar/ler o canal '📜・logs-vendas' no servidor %s.",
                guild.name,
            )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if is_authorized_guild(guild.id):
            logger.info("Bot adicionado ao servidor autorizado: %s (id=%s)", guild.name, guild.id)
            return

        logger.warning(
            "Bot adicionado a um servidor NÃO autorizado: %s (id=%s). GUILD_ID configurado: %s. Saindo do servidor.",
            guild.name,
            guild.id,
            settings.guild_id,
        )
        await self._leave_unauthorized_guild(guild)

    async def _leave_unauthorized_guild(self, guild: discord.Guild) -> None:
        message = (
            "⚠ Este bot é de uso exclusivo de uma comunidade específica e não está "
            "configurado para funcionar neste servidor. Ele vai sair automaticamente."
        )
        channel = guild.system_channel
        if channel is None:
            channel = next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                None,
            )
        if channel is not None:
            try:
                await channel.send(message)
            except discord.HTTPException:
                logger.warning("Não foi possível enviar aviso de servidor não autorizado em %s.", guild.name)

        await guild.leave()


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Handler genérico de erro, registrado em main.py via bot.tree.on_error.

    Primeiro tenta os handlers especializados (ex: permissão); se nenhum
    tratar, loga o erro completo e avisa o usuário de forma genérica —
    assim nenhuma exceção quebra a interação silenciosamente.
    """

    if await handle_permission_error(interaction, error):
        return

    logger.exception("Erro não tratado no comando '%s'", interaction.command.name if interaction.command else "?", exc_info=error)

    message = "⚠ Ocorreu um erro inesperado ao executar este comando. A equipe já foi notificada pelos logs."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        # interação já expirou (>15min) — nada a fazer além de logar, o que já foi feito acima
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
