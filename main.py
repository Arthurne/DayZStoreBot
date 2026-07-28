"""
Ponto de entrada do bot.

Rodar:
    python main.py

Responsabilidades deste arquivo (só isso — o resto mora nos módulos):
  1. Configurar logging.
  2. Inicializar o banco de dados (criar tabelas se não existirem).
  3. Criar a instância do bot com os intents necessários.
  4. Carregar bot/events.py e todos os cogs de comandos/ automaticamente.
  5. Registrar o handler global de erro de slash command.
  6. Conectar no Discord com o token do .env.
"""

from __future__ import annotations

import asyncio
import logging
import pkgutil

import discord
import uvicorn
from discord.ext import commands

import commands as commands_package
from bot.events import on_app_command_error
from config import settings
from database.database import init_db
from logs.logger import setup_logging
from store.purchases import register_persistent_approval_views
from store.shop_channels import register_persistent_buy_views
from ui.views import MyDeliveriesView, SteamConnectView

logger = logging.getLogger(__name__)

# members: necessário pra trocar apelido do usuário (Etapa 4) e resolver
# discord.Member em checagens de permissão.
intents = discord.Intents.default()
intents.members = True


class DayZStoreBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # prefixo "!" nunca é usado de fato (o bot é 100% slash command /
        # botão / modal) — discord.py exige algum valor mesmo assim.

    async def setup_hook(self):
        await init_db()

        # Views persistentes (timeout=None) precisam ser registradas aqui,
        # antes do bot conectar — senão, depois de um restart, os cliques em
        # botões enviados numa sessão anterior param de funcionar.
        self.add_view(MyDeliveriesView())
        if settings.steam_enabled:
            self.add_view(SteamConnectView())
        else:
            logger.info(
                "Steam desabilitada (%s). O bot Discord continua funcionando normalmente, "
                "mas o login/vínculo de Steam fica indisponível.",
                settings.steam_disabled_reason,
            )
        await register_persistent_buy_views(self)
        await register_persistent_approval_views(self)

        await self.load_extension("bot.events")
        await self._load_command_cogs()

        self.tree.on_error = on_app_command_error

        guild = discord.Object(id=settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info("%d comando(s) sincronizado(s) no servidor %s.", len(synced), settings.guild_id)

    async def _load_command_cogs(self) -> None:
        """Carrega automaticamente todo módulo dentro de commands/ que
        exponha uma função setup() (ou seja, seja um cog válido).

        Isso evita ter que lembrar de adicionar cada novo comando aqui
        manualmente — basta criar o arquivo em commands/ com uma
        função `async def setup(bot): ...` que ele já é carregado.
        """

        loaded = 0
        for module_info in pkgutil.iter_modules(commands_package.__path__):
            if module_info.ispkg:
                continue
            extension_name = f"commands.{module_info.name}"
            try:
                await self.load_extension(extension_name)
                loaded += 1
                logger.info("Cog carregado: %s", extension_name)
            except commands.NoEntryPointError:
                logger.debug("Ignorando %s (sem função setup()).", extension_name)
            except Exception:
                logger.exception("Falha ao carregar o cog %s", extension_name)

        if loaded == 0:
            logger.warning("Nenhum cog encontrado em commands/ ainda (esperado até a Etapa 5).")


async def main() -> None:
    setup_logging()
    bot = DayZStoreBot()

    async with bot:
        if settings.steam_enabled:
            # Import tardio de propósito: se a Steam está desligada, nem o
            # módulo do FastAPI (nem seus imports) precisam ser carregados.
            from steam.web import app as steam_api_app

            # A API do callback Steam roda no MESMO processo/loop do bot
            # (ver steam/web.py) — precisa de acesso direto ao client do
            # discord.py pra trocar apelido assim que o login é validado.
            steam_api_app.state.discord_bot = bot
            uvicorn_config = uvicorn.Config(
                steam_api_app, host=settings.web_host, port=settings.web_port, log_level=settings.log_level.lower()
            )
            web_server = uvicorn.Server(uvicorn_config)

            await asyncio.gather(
                bot.start(settings.discord_token),
                web_server.serve(),
            )
        else:
            logger.info(
                "Servidor web (callback Steam) não será iniciado — Steam desabilitada (%s).",
                settings.steam_disabled_reason,
            )
            await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
