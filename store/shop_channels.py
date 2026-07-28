"""
Parte "Discord" do domínio de loja: categoria 📁 LOJA DAYZ, um canal por
CATEGORIA de produto (não um canal por produto — várias mensagens de
produto podem morar no mesmo canal, exatamente como no exemplo do spec:

    📁 LOJA DAYZ
    ├── 🔫・armas
    ├── 🎒・kits
    ├── ⭐・vip
    └── 🚗・veiculos

A regra de negócio pura (banco) fica em store/products.py — este arquivo só
cuida de canal/categoria/embed/mensagem.
"""

from __future__ import annotations

import logging
import re
import unicodedata

import discord
from discord.ext import commands
from sqlalchemy import select

from database.database import get_session
from database.models import Product

logger = logging.getLogger(__name__)

SHOP_CATEGORY_NAME = "📁 LOJA DAYZ"

# Emojis conhecidos pras categorias mais comuns de servidor DayZ — puramente
# estético (nome do canal). Categoria fora dessa lista cai no emoji padrão.
_CATEGORY_EMOJIS = {
    "arma": "🔫", "armas": "🔫",
    "kit": "🎒", "kits": "🎒",
    "vip": "⭐",
    "veiculo": "🚗", "veiculos": "🚗", "veículo": "🚗", "veículos": "🚗",
    "moeda": "💰", "moedas": "💰",
    "geral": "📦",
}
_DEFAULT_EMOJI = "📦"


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "geral"


def _category_channel_name(category: str) -> str:
    emoji = _CATEGORY_EMOJIS.get(category.strip().lower(), _DEFAULT_EMOJI)
    return f"{emoji}・{_slugify(category)}"


async def ensure_shop_category(guild: discord.Guild) -> discord.CategoryChannel:
    existing = discord.utils.get(guild.categories, name=SHOP_CATEGORY_NAME)
    if existing:
        return existing
    category = await guild.create_category(SHOP_CATEGORY_NAME)
    logger.info("Categoria '%s' criada no servidor %s.", SHOP_CATEGORY_NAME, guild.name)
    return category


async def ensure_category_channel(guild: discord.Guild, category: str) -> discord.TextChannel:
    """Um canal por CATEGORIA de produto, criado (ou reaproveitado) dentro
    da categoria da loja. Vários produtos da mesma categoria compartilham o
    mesmo canal."""

    shop_category = await ensure_shop_category(guild)
    channel_name = _category_channel_name(category)

    existing = discord.utils.get(shop_category.text_channels, name=channel_name)
    if existing:
        return existing

    channel = await guild.create_text_channel(channel_name, category=shop_category)
    logger.info("Canal de categoria '%s' criado em %s.", channel_name, SHOP_CATEGORY_NAME)
    return channel


def build_product_embed(product: Product) -> discord.Embed:
    itens_fmt = "\n".join(f"✔ {item}" for item in product.items) or "—"
    status_suffix = "" if product.is_active else " — ❌ Indisponível"

    embed = discord.Embed(
        title=f"{product.name}{status_suffix}",
        description=f"**Descrição:**\n{product.description or '—'}\n\n**Inclui:**\n{itens_fmt}",
        color=discord.Color.gold() if product.is_active else discord.Color.dark_grey(),
    )
    embed.add_field(name="Valor", value=f"R${float(product.price):.2f}")
    if product.image_url:
        embed.set_image(url=product.image_url)
    return embed


async def sync_product_message(bot: commands.Bot, product: Product) -> None:
    """Garante que a mensagem de venda do produto existe e está atualizada.

    - Produto novo (sem channel_id/message_id) -> posta mensagem nova.
    - Produto existente, categoria não mudou -> edita a mensagem no lugar.
    - Produto existente, categoria mudou -> apaga a mensagem antiga e posta
      uma nova no canal da categoria nova (mensagens não "pulam" de canal,
      então recriar é a única opção).
    """

    guild = bot.get_guild(_guild_id())
    if guild is None:
        logger.error("Não foi possível sincronizar produto '%s': bot fora do servidor configurado.", product.name)
        return

    target_channel = await ensure_category_channel(guild, product.category)

    current_channel = guild.get_channel(product.channel_id) if product.channel_id else None
    same_channel = current_channel is not None and current_channel.id == target_channel.id

    view = _build_buy_view(product) if product.is_active else _build_disabled_view()

    if same_channel and product.message_id:
        try:
            message = await current_channel.fetch_message(product.message_id)
            await message.edit(embed=build_product_embed(product), view=view)
            return
        except discord.NotFound:
            pass  # mensagem foi apagada manualmente — cai pro fluxo de repostagem abaixo

    # categoria mudou (ou mensagem antiga sumiu) -> apaga a antiga, se existir, e posta nova
    if current_channel is not None and product.message_id:
        try:
            old_message = await current_channel.fetch_message(product.message_id)
            await old_message.delete()
        except discord.NotFound:
            pass

    new_message = await target_channel.send(embed=build_product_embed(product), view=view)

    async with get_session() as session:
        db_product = await session.get(Product, product.id)
        if db_product:
            db_product.channel_id = target_channel.id
            db_product.message_id = new_message.id
            await session.commit()

    logger.info("Mensagem de venda sincronizada para '%s' em #%s.", product.name, target_channel.name)


async def delete_product_message(bot: commands.Bot, *, channel_id: int | None, message_id: int | None) -> None:
    """Apaga só a MENSAGEM do produto — o canal é compartilhado pela
    categoria inteira, então nunca é apagado aqui."""

    if not channel_id or not message_id:
        return

    guild = bot.get_guild(_guild_id())
    if guild is None:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except discord.NotFound:
        pass


async def register_persistent_buy_views(bot: commands.Bot) -> None:
    """Chamado uma vez no startup (main.py) — re-registra o botão Comprar
    de todo produto ativo já existente, senão os cliques em mensagens
    antigas param de responder depois de um restart do bot."""

    async with get_session() as session:
        result = await session.execute(select(Product).where(Product.is_active.is_(True)))
        products = result.scalars().all()

    for product in products:
        bot.add_view(_build_buy_view(product))

    logger.info("%d view(s) persistente(s) de 'Comprar' registrada(s).", len(products))


def _build_buy_view(product: Product) -> discord.ui.View:
    from ui.views import BuyButtonView

    return BuyButtonView(product.id)


def _build_disabled_view() -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(label="Indisponível", emoji="🛒", style=discord.ButtonStyle.secondary, disabled=True)
    )
    return view


def _guild_id() -> int:
    from config import settings

    return settings.guild_id
