"""
/entregas — painel administrativo da fila de entregas.

Lista as entregas (dropdown, mesmo padrão de /produtos) e, ao escolher uma,
mostra os botões Processar / Marcar como entregue / Marcar como falhou /
Cancelar (DeliveryManageView, em ui/views.py).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.permissions import admin_only
from delivery.queue import STATUS_EMOJI, list_deliveries
from ui.views import DeliveryManageView


class DeliveriesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="entregas", description="Painel administrativo da fila de entregas")
    @admin_only()
    async def entregas(self, interaction: discord.Interaction):
        deliveries = await list_deliveries()

        if not deliveries:
            await interaction.response.send_message("📦 Nenhuma entrega registrada ainda.", ephemeral=True)
            return

        embed = discord.Embed(title="📦 Fila de Entregas", color=discord.Color.blurple())
        for d in deliveries[:25]:
            emoji = STATUS_EMOJI.get(d.status, "⚪")
            embed.add_field(
                name=f"#{d.id} — {d.product}",
                value=f"Pedido #{d.purchase_id} — SteamID {d.steam_id}\n{emoji} {d.status.value}",
                inline=False,
            )

        options = [
            discord.SelectOption(
                label=f"#{d.id} — {d.product}",
                value=f"{d.id}:{d.purchase_id}",
                description=f"{d.status.value} — SteamID {d.steam_id}",
                emoji=STATUS_EMOJI.get(d.status, "⚪"),
            )
            for d in deliveries[:25]
        ]
        select = discord.ui.Select(placeholder="Escolha uma entrega para gerenciar...", options=options)

        async def on_select(select_interaction: discord.Interaction):
            delivery_id_str, purchase_id_str = select_interaction.data["values"][0].split(":")
            await select_interaction.response.send_message(
                f"Gerenciando entrega #{delivery_id_str}:",
                view=DeliveryManageView(int(delivery_id_str), purchase_id=int(purchase_id_str)),
                ephemeral=True,
            )

        select.callback = on_select
        view = discord.ui.View(timeout=180)
        view.add_item(select)

        if len(deliveries) > 25:
            embed.set_footer(text="Mostrando só as 25 entregas mais recentes.")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeliveriesCog(bot))
