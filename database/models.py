"""
Modelos do banco de dados.

Como o bot atende uma única comunidade, não existe coluna de guild/tenant
em nenhuma tabela — isso é o que mais simplifica esse schema em relação a
uma versão SaaS.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Usuário (vínculo Discord <-> Steam)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    discord_name: Mapped[str] = mapped_column(String(100))

    steam_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    steam_name: Mapped[str] = mapped_column(String(100))
    steam_avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="user")


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    category: Mapped[str] = mapped_column(String(50), default="Geral")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Itens que a entrega vai aplicar no servidor DayZ (lista simples de strings,
    # ex: ["AK74", "Munição", "Carregadores"])
    items: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Preenchidos automaticamente quando o bot posta a mensagem de venda —
    # permitem editar/apagar a mensagem depois (ex: em /produto editar).
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="product")


# ---------------------------------------------------------------------------
# Compra
# ---------------------------------------------------------------------------
class PurchaseStatus(str, enum.Enum):
    pendente = "PENDENTE"
    pago = "PAGO"
    entregue = "ENTREGUE"
    cancelado = "CANCELADO"


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    steam_id: Mapped[str] = mapped_column(String(30), index=True)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    price: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[PurchaseStatus] = mapped_column(Enum(PurchaseStatus), default=PurchaseStatus.pendente)

    # --- Preparação para pagamento (Etapa 7) — nada disso é usado ainda,
    # só existe pra não precisar de outra migração quando PIX/API entrar. ---
    payment_transaction_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # id no gateway (PIX/Mercado Pago/etc.)
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # "pix", "mercadopago", "manual"...
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # observação livre do admin sobre a compra

    # Canal privado de atendimento desta compra (Etapa 6), se for criado.
    support_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="purchases")
    product: Mapped["Product"] = relationship(back_populates="purchases")
    delivery: Mapped["Delivery"] = relationship(back_populates="purchase", uselist=False)


# ---------------------------------------------------------------------------
# Entrega
# ---------------------------------------------------------------------------
class DeliveryStatus(str, enum.Enum):
    pendente = "Pendente"
    processando = "Processando"
    entregue = "Entregue"
    falhou = "Falhou"


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"), unique=True)
    steam_id: Mapped[str] = mapped_column(String(30), index=True)
    product: Mapped[str] = mapped_column(String(100))  # nome do produto no momento da entrega (histórico)
    items: Mapped[list[str]] = mapped_column(JSON, default=list)

    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.pendente)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Preparação para integrações futuras (RCON/API/Mod/Webhook) —
    # nullable, não usado de verdade ainda nesta etapa. ---
    delivery_method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # "manual", "rcon", "api", "mod", "webhook"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # motivo, se status = Falhou
    processed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # discord_id do admin que processou

    purchase: Mapped["Purchase"] = relationship(back_populates="delivery")
