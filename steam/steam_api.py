"""
Wrapper fino sobre a Steam Web API. Só usamos GetPlayerSummaries por
enquanto (nick, avatar, link do perfil) — se precisarmos de mais dados da
Steam no futuro (ex: VAC bans, tempo de jogo), entra aqui.
"""

from __future__ import annotations

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"


async def fetch_player_summary(steam_id64: str) -> dict | None:
    """Retorna {steam_id, nickname, avatar_url, profile_url} ou None se a
    Steam API não retornar dados pra esse SteamID (perfil deletado/banido/etc.)."""

    params = {"key": settings.steam_api_key, "steamids": steam_id64}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(PLAYER_SUMMARIES_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.exception("Falha ao consultar Steam Web API para SteamID %s", steam_id64)
        return None

    players = data.get("response", {}).get("players", [])
    if not players:
        logger.warning("Steam Web API não retornou dados para SteamID %s", steam_id64)
        return None

    player = players[0]
    return {
        "steam_id": player.get("steamid"),
        "nickname": player.get("personaname") or "Jogador",
        "avatar_url": player.get("avatarfull"),
        "profile_url": player.get("profileurl"),
    }
