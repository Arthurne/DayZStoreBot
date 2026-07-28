"""
Login "Conectar Steam" via OpenID 2.0 (é o protocolo oficial que a própria
Steam usa para logins de terceiros — não existe API de login mais moderna
pra Steam, então isso não é uma escolha de "versão antiga por preguiça").

Fluxo:
  1. build_login_url() gera o link que o botão do Discord abre no navegador.
  2. O usuário loga na Steam, que redireciona pra STEAM_OPENID_RETURN_URL
     com parâmetros de verificação.
  3. verify_openid_response() reenvia esses parâmetros pra Steam pedindo
     confirmação (check_authentication) e extrai o SteamID64 se for válido.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from config import settings

logger = logging.getLogger(__name__)

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
STEAM_ID_PREFIX = "https://steamcommunity.com/openid/id/"


def build_login_url(*, state: str) -> str:
    """`state` carrega o discord_id de quem clicou, pra sabermos, quando a
    Steam redirecionar de volta, a qual usuário Discord associar o vínculo."""

    return_to = f"{settings.steam_openid_return_url}?state={state}"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": settings.steam_openid_realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urlencode(params)}"


async def verify_openid_response(query_params: dict) -> str | None:
    """Reenvia os parâmetros pra Steam confirmando a autenticidade da
    resposta (evita que alguém forje um retorno de login). Retorna o
    SteamID64 se válido, ou None."""

    verify_params = dict(query_params)
    verify_params["openid.mode"] = "check_authentication"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(STEAM_OPENID_URL, data=verify_params)
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Falha ao validar resposta OpenID com a Steam")
        return None

    if "is_valid:true" not in resp.text:
        logger.warning("Resposta OpenID inválida ou expirada (is_valid:false)")
        return None

    claimed_id = query_params.get("openid.claimed_id", "")
    if not claimed_id.startswith(STEAM_ID_PREFIX):
        logger.warning("claimed_id fora do formato esperado: %s", claimed_id)
        return None

    return claimed_id.removeprefix(STEAM_ID_PREFIX)
