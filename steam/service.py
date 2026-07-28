"""
Ponto único que liga "login Steam validado" -> "gravar no banco" ->
"trocar apelido no Discord" -> "logar o resultado".

Chamado pelo callback HTTP (steam/web.py) depois que o OpenID já foi
validado e os dados do perfil já foram buscados na Steam Web API — este
módulo não sabe nada de HTTP, só de regra de negócio, o que facilita testar
e reaproveitar (ex: um comando administrativo futuro de re-vincular).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord
from discord.ext import commands
from sqlalchemy import select

from config import settings
from database.database import get_session
from database.models import User

logger = logging.getLogger(__name__)

NICKNAME_MAX_LENGTH = 32  # limite do Discord para apelidos


@dataclass
class LinkResult:
    success: bool
    message: str
    user: User | None = None
    nickname_changed: bool = False
    nickname_error: str | None = None


async def get_linked_user(discord_id: int) -> User | None:
    """Usado pelo sistema de compras (store/purchases.py) pra checar se o
    comprador já tem Steam vinculada, sem duplicar a query aqui."""

    async with get_session() as session:
        result = await session.execute(select(User).where(User.discord_id == discord_id))
        return result.scalar_one_or_none()


async def link_steam_account(bot: commands.Bot, *, discord_id: int, discord_name: str, steam_data: dict) -> LinkResult:
    steam_id = steam_data["steam_id"]
    steam_name = steam_data["nickname"]
    steam_avatar = steam_data.get("avatar_url")

    async with get_session() as session:
        # 1. Essa conta Steam já está vinculada a OUTRO Discord?
        result = await session.execute(select(User).where(User.steam_id == steam_id))
        existing_by_steam = result.scalar_one_or_none()

        if existing_by_steam and existing_by_steam.discord_id != discord_id:
            logger.warning(
                "Tentativa de vincular SteamID %s (já vinculada ao discord_id=%s) ao discord_id=%s",
                steam_id, existing_by_steam.discord_id, discord_id,
            )
            return LinkResult(
                success=False,
                message=(
                    "⚠ Esta conta Steam já está vinculada a outro usuário Discord neste servidor. "
                    "Se isso for um engano, contate um administrador."
                ),
            )

        # 2. Esse Discord já tem vínculo? (re-login / atualização de nick)
        result = await session.execute(select(User).where(User.discord_id == discord_id))
        user = result.scalar_one_or_none()

        if user:
            user.discord_name = discord_name
            user.steam_id = steam_id
            user.steam_name = steam_name
            user.steam_avatar = steam_avatar
        else:
            user = User(
                discord_id=discord_id,
                discord_name=discord_name,
                steam_id=steam_id,
                steam_name=steam_name,
                steam_avatar=steam_avatar,
            )
            session.add(user)

        await session.commit()
        await session.refresh(user)

    logger.info("Steam vinculada: discord_id=%s -> steam_id=%s (%s)", discord_id, steam_id, steam_name)

    nickname_changed, nickname_error = await _apply_nickname(bot, discord_id, steam_name)

    return LinkResult(
        success=True,
        message=f"✅ Steam vinculada com sucesso: {steam_name}",
        user=user,
        nickname_changed=nickname_changed,
        nickname_error=nickname_error,
    )


async def _apply_nickname(bot: commands.Bot, discord_id: int, steam_name: str) -> tuple[bool, str | None]:
    """Troca o apelido do usuário pro nome da Steam, cortando se passar do
    limite do Discord. Trata explicitamente a falta de permissão do bot
    (cargo do bot abaixo do usuário, ou falta de 'Gerenciar Apelidos')."""

    guild = bot.get_guild(settings.guild_id)
    if guild is None:
        error = "Bot não está no servidor configurado (GUILD_ID) — apelido não alterado."
        logger.error(error)
        return False, error

    member = guild.get_member(discord_id)
    if member is None:
        try:
            member = await guild.fetch_member(discord_id)
        except discord.NotFound:
            error = "Usuário não encontrado no servidor — apelido não alterado."
            logger.warning(error)
            return False, error

    new_nick = steam_name[:NICKNAME_MAX_LENGTH]

    try:
        await member.edit(nick=new_nick)
        logger.info("Apelido alterado: discord_id=%s -> '%s'", discord_id, new_nick)
        return True, None
    except discord.Forbidden:
        error = (
            "Sem permissão para alterar o apelido deste usuário "
            "(o cargo do bot precisa estar ACIMA do cargo do usuário, e o bot precisa "
            "da permissão 'Gerenciar Apelidos'. Donos do servidor nunca podem ter o apelido alterado por bots.)"
        )
        logger.warning("Falha ao trocar apelido (Forbidden): discord_id=%s — %s", discord_id, error)
        return False, error
    except discord.HTTPException as exc:
        error = f"Erro do Discord ao trocar apelido: {exc}"
        logger.exception("Falha ao trocar apelido (HTTPException): discord_id=%s", discord_id)
        return False, error
