"""
Sistema de permissões administrativas + proteção de servidor autorizado.

Nesta versão (comunidade única, sem cargo administrador configurável pelo
banco), "ser admin" = ter a permissão nativa `administrator` no servidor.
Centralizado aqui para que, se no futuro quisermos aceitar também um cargo
específico (ex: "Dono da Loja"), a mudança seja num único lugar.

Além disso, como o bot foi projetado pra UMA comunidade só (GUILD_ID fixo
no .env), qualquer interação vinda de outro servidor é bloqueada aqui —
ver NotAuthorizedGuild / is_authorized_guild.
"""

from __future__ import annotations

import discord
from discord import app_commands

from config import settings


class NotAuthorizedGuild(app_commands.CheckFailure):
    """Erro específico pra distinguir 'servidor errado' de 'sem permissão de admin'
    no handler de erros (mensagens diferentes, log diferente)."""


def is_authorized_guild(guild_id: int | None) -> bool:
    return guild_id == settings.guild_id


def is_admin_member(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


def admin_only():
    """Decorator para slash commands: bloqueia quem não é administrador
    E bloqueia qualquer uso fora do servidor autorizado (GUILD_ID).

    Uso:
        @app_commands.command(...)
        @admin_only()
        async def setup(self, interaction: discord.Interaction):
            ...
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_authorized_guild(interaction.guild_id):
            raise NotAuthorizedGuild()
        if not isinstance(interaction.user, discord.Member):
            return False
        return is_admin_member(interaction.user)

    return app_commands.check(predicate)


async def handle_permission_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> bool:
    """Retorna True se o erro foi tratado aqui (permissão/servidor), False se
    deve subir pro handler genérico de erros."""

    if isinstance(error, NotAuthorizedGuild):
        message = "⚠ Este bot não está configurado para funcionar neste servidor."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return True

    if isinstance(error, app_commands.CheckFailure):
        message = "⚠ Você precisa ser administrador do servidor para usar este comando."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return True
    return False

