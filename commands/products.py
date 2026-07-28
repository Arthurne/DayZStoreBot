"""
/produto criar|editar|remover|desativar e /produtos.

Todos os comandos são administrativos (@admin_only — já bloqueia servidor
errado e usuário sem permissão, ver bot/permissions.py). O jogador nunca
interage com este arquivo: ele só vê a mensagem que o bot posta e clica em
Comprar (BuyButtonView, em ui/views.py).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.permissions import admin_only
from store import products as products_service
from store import shop_channels
from ui.modals import start_product_modal
from ui.views import ProductListSelect, ProductManageView

logger = logging.getLogger(__name__)


class ProdutoGroup(app_commands.Group):
    def __init__(self, bot: commands.Bot):
        super().__init__(name="produto", description="Gerenciar produtos da loja")
        self.bot = bot

    @app_commands.command(name="criar", description="Criar um novo produto na loja")
    @admin_only()
    async def criar(self, interaction: discord.Interaction):
        await start_product_modal(interaction, on_complete=self._handle_create)

    async def _handle_create(self, interaction: discord.Interaction, data: dict) -> None:
        product = await products_service.create_product(
            name=data["name"],
            description=data["description"],
            price=data["price"],
            category=data["category"],
            items=data["items"],
            image_url=data["image_url"],
        )
        await shop_channels.sync_product_message(self.bot, product)

        await interaction.response.send_message(
            f"✅ Produto **{product.name}** criado em **{product.category}**.", ephemeral=True
        )
        logger.info("Produto '%s' criado por %s (id=%s)", product.name, interaction.user, interaction.user.id)

    @app_commands.command(name="editar", description="Editar um produto existente pelo nome")
    @admin_only()
    async def editar(self, interaction: discord.Interaction, nome: str):
        product = await products_service.get_product_by_name(nome)
        if product is None:
            await interaction.response.send_message(f"⚠ Produto **{nome}** não encontrado.", ephemeral=True)
            return

        defaults = {
            "name": product.name,
            "description": product.description,
            "price": float(product.price),
            "category": product.category,
            "items": product.items,
            "image_url": product.image_url,
        }
        await start_product_modal(
            interaction,
            on_complete=self._make_edit_handler(product.id),
            defaults=defaults,
            editing=True,
        )

    def _make_edit_handler(self, product_id: int):
        async def handler(interaction: discord.Interaction, data: dict) -> None:
            product = await products_service.update_product(
                product_id,
                name=data["name"],
                description=data["description"],
                price=data["price"],
                category=data["category"],
                items=data["items"],
                image_url=data["image_url"],
            )
            if product is None:
                await interaction.response.send_message("⚠ Produto não encontrado (pode ter sido removido).", ephemeral=True)
                return

            await shop_channels.sync_product_message(self.bot, product)
            await interaction.response.send_message(f"✅ Produto **{product.name}** atualizado.", ephemeral=True)
            logger.info("Produto '%s' (id=%s) editado por %s", product.name, product_id, interaction.user)

        return handler

    @app_commands.command(name="remover", description="Remover definitivamente um produto pelo nome")
    @admin_only()
    async def remover(self, interaction: discord.Interaction, nome: str):
        product = await products_service.get_product_by_name(nome)
        if product is None:
            await interaction.response.send_message(f"⚠ Produto **{nome}** não encontrado.", ephemeral=True)
            return

        removed = await products_service.delete_product(product.id)
        await shop_channels.delete_product_message(
            self.bot, channel_id=removed.channel_id, message_id=removed.message_id
        )

        await interaction.response.send_message(f"🗑 Produto **{nome}** removido definitivamente.", ephemeral=True)
        logger.info("Produto '%s' removido por %s", nome, interaction.user)

    @app_commands.command(name="desativar", description="Ativar/desativar um produto (sem apagar) pelo nome")
    @admin_only()
    async def desativar(self, interaction: discord.Interaction, nome: str):
        product = await products_service.get_product_by_name(nome)
        if product is None:
            await interaction.response.send_message(f"⚠ Produto **{nome}** não encontrado.", ephemeral=True)
            return

        updated = await products_service.set_active(product.id, not product.is_active)
        await shop_channels.sync_product_message(self.bot, updated)

        status = "ativado ✅" if updated.is_active else "desativado ⛔"
        await interaction.response.send_message(f"Produto **{updated.name}** {status}.", ephemeral=True)
        logger.info("Produto '%s' %s por %s", updated.name, status, interaction.user)


class ProductsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.tree.add_command(ProdutoGroup(bot))

    @app_commands.command(name="produtos", description="Listar e gerenciar os produtos cadastrados")
    @admin_only()
    async def produtos(self, interaction: discord.Interaction):
        products = await products_service.list_products()

        if not products:
            await interaction.response.send_message("📦 Nenhum produto cadastrado ainda. Use `/produto criar`.", ephemeral=True)
            return

        embed = discord.Embed(title="📦 Produtos cadastrados", color=discord.Color.blurple())
        for p in products:
            status = "✅ Ativo" if p.is_active else "⛔ Inativo"
            embed.add_field(name=f"{p.name}", value=f"{p.category} — R${float(p.price):.2f} — {status}", inline=False)

        view = ProductListSelect(products) if len(products) <= 25 else None
        if view is None:
            await interaction.response.send_message(
                embed=embed,
                content="⚠ Mais de 25 produtos: mostrando só a lista, use `/produto editar <nome>` diretamente.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ---------------------------------------------------------------------------
# Chamados pelos botões de ProductManageView (ui/views.py) via import tardio
# ---------------------------------------------------------------------------
async def start_edit_flow(interaction: discord.Interaction, product_id: int) -> None:
    product = await products_service.get_product_by_id(product_id)
    if product is None:
        await interaction.response.send_message("⚠ Produto não encontrado.", ephemeral=True)
        return

    bot = interaction.client

    defaults = {
        "name": product.name,
        "description": product.description,
        "price": float(product.price),
        "category": product.category,
        "items": product.items,
        "image_url": product.image_url,
    }

    async def handler(modal_interaction: discord.Interaction, data: dict) -> None:
        updated = await products_service.update_product(
            product_id,
            name=data["name"],
            description=data["description"],
            price=data["price"],
            category=data["category"],
            items=data["items"],
            image_url=data["image_url"],
        )
        if updated is None:
            await modal_interaction.response.send_message("⚠ Produto não encontrado (pode ter sido removido).", ephemeral=True)
            return
        await shop_channels.sync_product_message(bot, updated)
        await modal_interaction.response.send_message(f"✅ Produto **{updated.name}** atualizado.", ephemeral=True)
        logger.info("Produto '%s' (id=%s) editado por %s", updated.name, product_id, modal_interaction.user)

    await start_product_modal(interaction, on_complete=handler, defaults=defaults, editing=True)


async def handle_delete_click(interaction: discord.Interaction, product_id: int) -> None:
    product = await products_service.get_product_by_id(product_id)
    name = product.name if product else "produto"

    removed = await products_service.delete_product(product_id)
    if removed is None:
        await interaction.response.send_message("⚠ Produto não encontrado (já removido).", ephemeral=True)
        return

    await shop_channels.delete_product_message(
        interaction.client, channel_id=removed.channel_id, message_id=removed.message_id
    )
    await interaction.response.send_message(f"🗑 Produto **{name}** removido definitivamente.", ephemeral=True)
    logger.info("Produto '%s' removido por %s (via /produtos)", name, interaction.user)


async def handle_toggle_click(interaction: discord.Interaction, product_id: int) -> None:
    product = await products_service.get_product_by_id(product_id)
    if product is None:
        await interaction.response.send_message("⚠ Produto não encontrado.", ephemeral=True)
        return

    updated = await products_service.set_active(product_id, not product.is_active)
    await shop_channels.sync_product_message(interaction.client, updated)

    status = "ativado ✅" if updated.is_active else "desativado ⛔"
    await interaction.response.send_message(f"Produto **{updated.name}** {status}.", ephemeral=True)
    logger.info("Produto '%s' %s por %s (via /produtos)", updated.name, status, interaction.user)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProductsCog(bot))
