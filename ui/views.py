"""
Componentes de UI (botões/modals). O que é do sistema Steam fica no topo
(como já estava); o que é do sistema de produtos/loja foi adicionado
abaixo. Regra de negócio real mora em store/ e steam/service.py — aqui é
só Discord.
"""

from __future__ import annotations

import discord
from sqlalchemy import select

from database.database import get_session
from database.models import User

from steam.steam_auth import build_login_url


class SteamConnectView(discord.ui.View):
    """View persistente (timeout=None) anexada à mensagem fixa do canal
    🎮・registro. Precisa ser re-registrada com `bot.add_view()` no
    startup para continuar funcionando depois de o bot reiniciar."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Conectar Steam", emoji="🔗", style=discord.ButtonStyle.primary, custom_id="steam:connect"
    )
    async def connect(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificação "já possui cadastro": evita mandar o usuário pra Steam
        # de novo à toa e deixa claro qual conta já está vinculada. Quem
        # quiser TROCAR a Steam vinculada pode clicar de novo mesmo assim
        # (o botão abaixo permite isso) — só não fazemos isso silenciosamente.
        async with get_session() as session:
            result = await session.execute(select(User).where(User.discord_id == interaction.user.id))
            existing = result.scalar_one_or_none()

        login_url = build_login_url(state=str(interaction.user.id))
        link_view = discord.ui.View()
        link_view.add_item(
            discord.ui.Button(label="Fazer login na Steam", url=login_url, style=discord.ButtonStyle.link)
        )

        if existing:
            await interaction.response.send_message(
                f"ℹ Você já está vinculado como **{existing.steam_name}**.\n"
                f"Se quiser trocar de conta Steam, clique no link abaixo para vincular uma nova:",
                view=link_view,
                ephemeral=True,
            )
            return

        # O link precisa ser gerado NA HORA do clique (não é um botão de
        # link estático) porque o `state` embute o discord_id de quem
        # clicou — é assim que o callback sabe a qual usuário associar o
        # vínculo quando a Steam redirecionar de volta.
        await interaction.response.send_message(
            "Clique no link abaixo para logar com sua conta Steam (link pessoal, válido só para você):",
            view=link_view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Sistema de produtos / loja (Etapa 5)
# ---------------------------------------------------------------------------
class BuyButtonView(discord.ui.View):
    """Anexada à mensagem de venda de cada produto. Persistente (timeout=None)
    — precisa de custom_id único por produto (embutido no product_id) pra
    sobreviver a um restart do bot; ver store/shop_channels.register_persistent_buy_views().
    """

    def __init__(self, product_id: int):
        super().__init__(timeout=None)
        self.product_id = product_id

        button = discord.ui.Button(
            label="Comprar", emoji="🛒", style=discord.ButtonStyle.success, custom_id=f"shop:buy:{product_id}"
        )
        button.callback = self._on_click
        self.add_item(button)

    async def _on_click(self, interaction: discord.Interaction):
        from store.purchases import handle_buy_click

        await handle_buy_click(interaction, self.product_id)


class ProductManageView(discord.ui.View):
    """Botões [Editar] [Excluir] [Ativar/Desativar] mostrados em /produtos
    depois que o admin escolhe um produto no ProductListSelect."""

    def __init__(self, product_id: int, *, is_active: bool):
        super().__init__(timeout=180)
        self.product_id = product_id

        toggle_label = "Desativar" if is_active else "Ativar"
        toggle_style = discord.ButtonStyle.secondary if is_active else discord.ButtonStyle.success

        editar = discord.ui.Button(label="Editar", emoji="✏", style=discord.ButtonStyle.primary)
        excluir = discord.ui.Button(label="Excluir", emoji="🗑", style=discord.ButtonStyle.danger)
        alternar = discord.ui.Button(label=toggle_label, emoji="⛔", style=toggle_style)

        editar.callback = self._editar
        excluir.callback = self._excluir
        alternar.callback = self._alternar

        self.add_item(editar)
        self.add_item(excluir)
        self.add_item(alternar)

    async def _editar(self, interaction: discord.Interaction):
        from commands.products import start_edit_flow

        await start_edit_flow(interaction, self.product_id)

    async def _excluir(self, interaction: discord.Interaction):
        from commands.products import handle_delete_click

        await handle_delete_click(interaction, self.product_id)

    async def _alternar(self, interaction: discord.Interaction):
        from commands.products import handle_toggle_click

        await handle_toggle_click(interaction, self.product_id)


class ProductListSelect(discord.ui.View):
    """Dropdown de até 25 produtos, usado por /produtos. Selecionar um
    produto mostra ProductManageView pra ele. Isso evita colocar dezenas de
    botões numa view só (Discord limita 25 componentes por mensagem)."""

    def __init__(self, products: list):
        super().__init__(timeout=180)

        options = [
            discord.SelectOption(
                label=f"{p.name} — R${float(p.price):.2f}",
                value=str(p.id),
                description=f"{p.category} · {'ativo' if p.is_active else 'inativo'}",
                emoji="✅" if p.is_active else "⛔",
            )
            for p in products[:25]
        ]
        select = discord.ui.Select(placeholder="Escolha um produto para gerenciar...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        from store.products import get_product_by_id

        product_id = int(interaction.data["values"][0])
        product = await get_product_by_id(product_id)
        if product is None:
            await interaction.response.send_message("⚠ Produto não encontrado (pode ter sido removido).", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{product.name}",
            description=f"{product.category} — R${float(product.price):.2f} — {'✅ ativo' if product.is_active else '⛔ inativo'}",
        )
        await interaction.response.send_message(
            embed=embed, view=ProductManageView(product.id, is_active=product.is_active), ephemeral=True
        )


# ---------------------------------------------------------------------------
# Sistema de compras (Etapa 6)
# ---------------------------------------------------------------------------
class ConfirmPurchaseView(discord.ui.View):
    """Botões [Confirmar] [Cancelar] da tela "CONFIRMAR COMPRA". Não é
    persistente (timeout=180) — é uma mensagem ephemeral de curta duração,
    não faz sentido sobreviver a um restart do bot."""

    def __init__(self, product_id: int):
        super().__init__(timeout=180)
        self.product_id = product_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        from store.purchases import handle_purchase_confirm

        await handle_purchase_confirm(interaction, self.product_id)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        from store.purchases import handle_purchase_cancel

        await handle_purchase_cancel(interaction, self.product_id)


# ---------------------------------------------------------------------------
# Aprovação manual de pagamento + entregas (Etapa 7)
# ---------------------------------------------------------------------------
class PurchaseApprovalView(discord.ui.View):
    """Anexada à mensagem do canal privado de atendimento do pedido
    (store/purchase_channels.py). Persistente — a aprovação pode acontecer
    dias depois e sobreviver a um restart do bot. Só quem tem permissão de
    administrador pode clicar (o comprador também tem acesso ao canal, mas
    não a estes botões)."""

    def __init__(self, purchase_id: int):
        super().__init__(timeout=None)
        self.purchase_id = purchase_id

        aprovar = discord.ui.Button(
            label="Aprovar Pagamento", emoji="✅", style=discord.ButtonStyle.success,
            custom_id=f"purchase:approve:{purchase_id}",
        )
        cancelar = discord.ui.Button(
            label="Cancelar Pedido", emoji="🚫", style=discord.ButtonStyle.danger,
            custom_id=f"purchase:cancelpay:{purchase_id}",
        )
        aprovar.callback = self._aprovar
        cancelar.callback = self._cancelar
        self.add_item(aprovar)
        self.add_item(cancelar)

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        from bot.permissions import is_admin_member

        if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
            await interaction.response.send_message("⚠ Só um administrador pode fazer isso.", ephemeral=True)
            return False
        return True

    async def _aprovar(self, interaction: discord.Interaction):
        if not await self._check_admin(interaction):
            return

        self.disable_all_items()
        await interaction.response.edit_message(view=self)

        from store.purchases import approve_payment

        result = await approve_payment(interaction.client, self.purchase_id, interaction.user.id)
        if result is None:
            await interaction.followup.send(
                "⚠ Não foi possível aprovar (pedido não existe mais ou já foi processado).", ephemeral=True
            )
            return

        purchase, delivery = result
        await interaction.followup.send(
            f"✅ Pagamento aprovado! Entrega #{delivery.id if delivery else '?'} criada com status **Pendente**.",
            ephemeral=True,
        )

    async def _cancelar(self, interaction: discord.Interaction):
        if not await self._check_admin(interaction):
            return

        self.disable_all_items()
        await interaction.response.edit_message(view=self)

        from store.purchases import cancel_purchase

        purchase = await cancel_purchase(interaction.client, self.purchase_id, interaction.user.id)
        if purchase is None:
            await interaction.followup.send(
                "⚠ Não foi possível cancelar (pedido não existe ou já foi entregue).", ephemeral=True
            )
            return

        await interaction.followup.send(f"🚫 Pedido #{self.purchase_id} cancelado.", ephemeral=True)


class MyDeliveriesView(discord.ui.View):
    """Botão fixo do canal 📦・entregas. Persistente, custom_id estático —
    não depende de nenhum id específico, então uma única instância serve
    pra sempre (diferente de PurchaseApprovalView/BuyButtonView)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Minhas Entregas", emoji="📦", style=discord.ButtonStyle.primary, custom_id="delivery:mine")
    async def minhas_entregas(self, interaction: discord.Interaction, button: discord.ui.Button):
        from steam.service import get_linked_user
        from delivery.queue import STATUS_EMOJI, list_deliveries_for_steam_id

        user = await get_linked_user(interaction.user.id)
        if user is None:
            await interaction.response.send_message(
                "🎮 Você precisa vincular sua Steam primeiro (canal 🎮・registro).", ephemeral=True
            )
            return

        deliveries = await list_deliveries_for_steam_id(user.steam_id)
        if not deliveries:
            await interaction.response.send_message("📦 Você ainda não tem nenhuma entrega registrada.", ephemeral=True)
            return

        embed = discord.Embed(title="📦 SUAS ENTREGAS", color=discord.Color.blurple())
        for d in deliveries[:25]:
            emoji = STATUS_EMOJI.get(d.status, "⚪")
            embed.add_field(name=f"{d.product} (pedido #{d.purchase_id})", value=f"Status:\n{emoji} {d.status.value}", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class FailDeliveryModal(discord.ui.Modal, title="Marcar entrega como Falhou"):
    motivo = discord.ui.TextInput(
        label="Motivo (opcional)", style=discord.TextStyle.paragraph, required=False, max_length=300
    )

    def __init__(self, delivery_id: int):
        super().__init__()
        self.delivery_id = delivery_id

    async def on_submit(self, interaction: discord.Interaction):
        from delivery.queue import set_failed

        delivery = await set_failed(
            self.delivery_id, admin_discord_id=interaction.user.id, reason=str(self.motivo.value or "").strip() or None
        )
        if delivery is None:
            await interaction.response.send_message("⚠ Entrega não encontrada.", ephemeral=True)
            return
        await interaction.response.send_message(f"❌ Entrega #{self.delivery_id} marcada como **Falhou**.", ephemeral=True)


class DeliveryManageView(discord.ui.View):
    """Botões do painel administrativo /entregas: Processar / Marcar como
    entregue / Marcar como falhou / Cancelar (cancela o PEDIDO inteiro, não
    é um novo status de entrega — ver store/purchases.cancel_purchase)."""

    def __init__(self, delivery_id: int, *, purchase_id: int):
        super().__init__(timeout=180)
        self.delivery_id = delivery_id
        self.purchase_id = purchase_id

        processar = discord.ui.Button(label="Processar", emoji="🔧", style=discord.ButtonStyle.primary)
        entregue = discord.ui.Button(label="Marcar como entregue", emoji="✅", style=discord.ButtonStyle.success)
        falhou = discord.ui.Button(label="Marcar como falhou", emoji="❌", style=discord.ButtonStyle.secondary)
        cancelar = discord.ui.Button(label="Cancelar", emoji="🚫", style=discord.ButtonStyle.danger)

        processar.callback = self._processar
        entregue.callback = self._entregue
        falhou.callback = self._falhou
        cancelar.callback = self._cancelar

        self.add_item(processar)
        self.add_item(entregue)
        self.add_item(falhou)
        self.add_item(cancelar)

    async def _processar(self, interaction: discord.Interaction):
        from delivery.queue import set_processing

        await set_processing(self.delivery_id, admin_discord_id=interaction.user.id)
        await interaction.response.send_message(f"🔧 Entrega #{self.delivery_id} marcada como **Processando**.", ephemeral=True)

    async def _entregue(self, interaction: discord.Interaction):
        from delivery.queue import set_delivered

        await set_delivered(self.delivery_id, admin_discord_id=interaction.user.id)
        await interaction.response.send_message(f"✅ Entrega #{self.delivery_id} marcada como **Entregue**.", ephemeral=True)

    async def _falhou(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FailDeliveryModal(self.delivery_id))

    async def _cancelar(self, interaction: discord.Interaction):
        from store.purchases import cancel_purchase

        purchase = await cancel_purchase(interaction.client, self.purchase_id, interaction.user.id)
        if purchase is None:
            await interaction.response.send_message(
                "⚠ Não foi possível cancelar (pedido não existe ou já foi entregue).", ephemeral=True
            )
            return
        await interaction.response.send_message(f"🚫 Pedido #{self.purchase_id} cancelado.", ephemeral=True)
