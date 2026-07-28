"""
Logging da aplicação (console/arquivo). O canal 📜・logs-vendas do Discord é
outra coisa — esse é alimentado pelo módulo de compras/entregas nas
Etapas 6/7, não por aqui.
"""

from __future__ import annotations

import logging
import sys

from config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(handler)

    # discord.py é bem verboso em DEBUG/INFO por padrão — mantemos em WARNING
    # pra não afogar os logs da aplicação, a menos que LOG_LEVEL=DEBUG.
    if level > logging.DEBUG:
        logging.getLogger("discord").setLevel(logging.WARNING)
