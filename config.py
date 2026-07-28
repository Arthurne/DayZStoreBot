"""
Configurações globais do bot, carregadas do arquivo .env.

Este projeto atende UMA ÚNICA comunidade Discord — por isso GUILD_ID é fixo
aqui (não existe conceito de "configuração por servidor" como num SaaS
multi-tenant). Configurações específicas da loja (nome, canais criados,
categoria de produtos etc.) não ficam aqui: ficam no banco de dados,
editáveis pelo /setup, porque podem mudar em tempo de execução sem reiniciar
o bot. Aqui só entram segredos e parâmetros de infraestrutura.

Só DISCORD_TOKEN e GUILD_ID são realmente obrigatórios pro bot subir. Tudo
relacionado à Steam é OPCIONAL — pensado pra rodar em ambientes como Replit
ou uma máquina local sem precisar montar toda a infraestrutura de OpenID
antes de conseguir nem testar o bot Discord. Quem decide se a Steam está
"ligada" ou não é a property `steam_enabled` — é a ÚNICA fonte de verdade
disso no projeto inteiro; nenhum outro módulo deve checar STEAM_API_KEY ou
DEV_MODE diretamente, sempre `settings.steam_enabled`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"\n\nERRO:\n\n"
            f"{name} não configurado.\n\n"
            f"Configure a variável de ambiente '{name}' antes de iniciar o bot "
            f"(no Replit: aba Secrets; localmente: copie .env.example para .env "
            f"e preencha).\n"
        )
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Discord — únicas variáveis realmente obrigatórias
    discord_token: str
    guild_id: int

    # Modo de desenvolvimento — quando True, desativa Steam/FastAPI
    # independente do que estiver preenchido nas variáveis Steam abaixo.
    dev_mode: bool

    # Steam — OPCIONAL. Vazio (`""`) se não configurado; nada explode por
    # causa disso, ver `steam_enabled`/`steam_configured` abaixo.
    steam_api_key: str
    steam_openid_realm: str
    steam_openid_return_url: str

    # Servidor web interno (callback OpenID) — só sobe se steam_enabled
    web_host: str
    web_port: int

    # Banco de dados
    database_url: str

    # Ambiente
    log_level: str

    @property
    def steam_configured(self) -> bool:
        """Só olha se as 3 variáveis da Steam foram preenchidas — ignora
        DEV_MODE. Existe separado de `steam_enabled` só pra montar a
        mensagem de diagnóstico (`steam_disabled_reason`) com precisão."""

        return bool(self.steam_api_key and self.steam_openid_realm and self.steam_openid_return_url)

    @property
    def steam_enabled(self) -> bool:
        """Fonte única de verdade do projeto inteiro: a Steam só está
        "ligada" se NÃO estiver em DEV_MODE e as 3 variáveis estiverem
        preenchidas. Todo o resto do código (main.py, bot/events.py,
        ui/views.py, steam/*) consulta só esta property — nunca
        `os.getenv("STEAM_API_KEY")` nem `settings.dev_mode` diretamente."""

        return (not self.dev_mode) and self.steam_configured

    @property
    def steam_disabled_reason(self) -> str:
        """Mensagem amigável de por que a Steam está desligada — usada nos
        logs de startup (bot/events.py, main.py) em vez de cada lugar
        inventar seu próprio texto."""

        if self.steam_enabled:
            return ""
        if self.dev_mode:
            return "DEV_MODE=true está ativado"
        faltando = [
            name
            for name, value in (
                ("STEAM_API_KEY", self.steam_api_key),
                ("STEAM_OPENID_REALM", self.steam_openid_realm),
                ("STEAM_OPENID_RETURN_URL", self.steam_openid_return_url),
            )
            if not value
        ]
        return f"faltam as variáveis {', '.join(faltando)}"


def load_settings() -> Settings:
    return Settings(
        discord_token=_require("DISCORD_TOKEN"),
        guild_id=int(_require("GUILD_ID")),
        dev_mode=_bool_env("DEV_MODE", default=False),
        steam_api_key=os.getenv("STEAM_API_KEY", ""),
        steam_openid_realm=os.getenv("STEAM_OPENID_REALM", ""),
        steam_openid_return_url=os.getenv("STEAM_OPENID_RETURN_URL", ""),
        web_host=os.getenv("WEB_HOST", "0.0.0.0"),
        web_port=int(os.getenv("WEB_PORT", "8000")),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dayz_store.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


# Instância única, importada pelo resto do projeto: `from config import settings`
settings = load_settings()
