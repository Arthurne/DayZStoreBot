"""
GET /steam/callback — a Steam redireciona o navegador do usuário pra cá
depois do login OpenID.

Esse endpoint roda no MESMO processo/loop asyncio do bot (ver main.py),
porque precisa chamar `member.edit(nick=...)` diretamente no client do
discord.py logo depois de validar o login — rodar em processos separados
exigiria uma fila (Redis, etc.) só pra essa comunicação, desnecessário pro
tamanho desse projeto (uma comunidade só).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

from config import settings
from steam.service import link_steam_account
from steam.steam_api import fetch_player_summary
from steam.steam_auth import verify_openid_response

logger = logging.getLogger(__name__)

app = FastAPI(title="DayZ Store Bot — Steam Auth")


def _page(title: str, message: str, ok: bool) -> HTMLResponse:
    color = "#2ecc71" if ok else "#e74c3c"
    html = f"""
    <html>
      <head><title>{title}</title></head>
      <body style="font-family: sans-serif; background:#1e1f22; color:#e5e5e5; text-align:center; padding-top:80px;">
        <h1 style="color:{color};">{title}</h1>
        <p>{message}</p>
        <p style="color:#999;">Você já pode voltar para o Discord.</p>
      </body>
    </html>
    """
    return HTMLResponse(html, status_code=200 if ok else 400)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/steam/callback", response_class=HTMLResponse)
async def steam_callback(request: Request, state: str = Query(...)):
    query_params = dict(request.query_params)

    try:
        discord_id = int(state)
    except ValueError:
        logger.warning("Callback Steam recebido com state inválido: %r", state)
        return _page("Link inválido", "O parâmetro de estado do link está corrompido. Gere um novo link no Discord.", ok=False)

    steam_id64 = await verify_openid_response(query_params)
    if not steam_id64:
        return _page("Falha na verificação", "Não foi possível validar o login com a Steam. Tente novamente.", ok=False)

    steam_data = await fetch_player_summary(steam_id64)
    if not steam_data:
        return _page(
            "Perfil Steam indisponível",
            "Login validado, mas não conseguimos ler os dados do seu perfil Steam "
            "(pode estar como privado). Deixe o perfil público e tente de novo.",
            ok=False,
        )

    bot = request.app.state.discord_bot
    guild = bot.get_guild(settings.guild_id)
    if guild is None:
        logger.error("Bot não está no servidor configurado (GUILD_ID=%s).", settings.guild_id)
        return _page("Erro de configuração", "O bot não está no servidor configurado. Avise um administrador.", ok=False)

    member = guild.get_member(discord_id)
    discord_name = member.display_name if member else "Desconhecido"

    result = await link_steam_account(bot, discord_id=discord_id, discord_name=discord_name, steam_data=steam_data)

    if not result.success:
        return _page("Não foi possível vincular", result.message, ok=False)

    extra = ""
    if not result.nickname_changed:
        extra = f"<br><small>⚠ Não foi possível atualizar seu apelido automaticamente: {result.nickname_error}</small>"

    return _page("✅ Steam vinculada com sucesso!", f"Bem-vindo, {steam_data['nickname']}!{extra}", ok=True)
