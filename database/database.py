"""
Engine e fábrica de sessões assíncronas.

Uso típico:

    from database.database import get_session

    async with get_session() as session:
        session.add(algo)
        await session.commit()

A troca de SQLite pra PostgreSQL é só mudar DATABASE_URL no .env — nada
neste arquivo precisa mudar (os dois dialetos são suportados pelo mesmo
código async do SQLAlchemy 2.x).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session():
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Cria as tabelas caso não existam. Chamado uma vez na inicialização do bot."""

    from database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Banco de dados pronto (%s)", settings.database_url)
