"""
Fluxo de compra do jogador. Nenhum comando aqui — tudo por clique
(🛒 Comprar -> Confirmar/Cancelar), o jogador nunca digita nada.

Esta etapa vai até criar o Purchase em PENDENTE + canal de atendimento +
logs. `mark_paid` / `mark_delivered` / `mark_cancelled` já existem prontos
pra Etapa 7 (pagamento/entrega) chamar — nada os aciona ainda.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from sqlalchemy import select

from database.database import get_session
from database.models import Product, Purchase, PurchaseStatus
from logs.sales_channel import log_purchase_event
from steam.service import get_linked_user
from store.purchase_channels import ensure_purchase_channel

logger = logging.getLogger(__name__)

# Proteção contra clique duplicado: enquanto um par (discord_id, product_id)
# está "em processamento" entre o clique e a resposta terminar, um segundo
# clique é ignorado. Além disso, a mensagem de confirmação perde os botões
# assim que clicada (ver _handle_purchase_confirm) — duas camadas de defesa.
# Um set em memória é suficiente pro volume de uma comunidade só; não
# sobrevive a um restart, mas nesse intervalo não há clique pendente mesmo.
_processing: set[tuple[int, int]] = set()


async def handle_buy_click(interaction: discord.Interaction, product_id: int) -> None:
    lock_key = (interaction.user.id, product_id)
    if lock_key in _processing:
        await interaction.response.send_message("⏳ Já estamos processando seu clique, aguarde um instante.", ephemeral=True)
        return

    _processing.add(lock_key)
    try:
        await _handle_buy_click(interaction, product_id)
    finally:
        _processing.discard(lock_key)


async def _handle_buy_click(interaction: discord.Interaction, product_id: int) -> None:
    user = await get_linked_user(interaction.user.id)

    async with get_session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            await interaction.response.send_message("⚠ Este produto não existe mais.", ephemeral=True)
            return

        if not product.is_active:
            await interaction.response.send_message("⚠ Este produto não está mais disponível.", ephemeral=True)
            return

        if user is None:
            await interaction.response.send_message(
                "🎮 Você precisa vincular sua Steam antes de comprar. "
                "Vá até o canal de registro e clique em **Conectar Steam**.",
                ephemeral=True,
            )
            return

        pending_result = await session.execute(
            select(Purchase).where(
                Purchase.discord_id == interaction.user.id,
                Purchase.product_id == product_id,
                Purchase.status == PurchaseStatus.pendente,
            )
        )
        pending = pending_result.scalar_one_or_none()

        # snapshot dos dados que a tela de confirmação precisa, antes de
        # fechar a sessão
        product_name, product_price, steam_name = product.name, product.price, user.steam_name

    if pending:
        await interaction.response.send_message(
            f"ℹ Você já tem uma compra pendente de **{product_name}** (pedido #{pending.id}). "
            f"Aguarde o atendimento antes de comprar de novo.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(title="CONFIRMAR COMPRA", color=discord.Color.orange())
    embed.add_field(name="Produto:", value=product_name, inline=False)
    embed.add_field(name="Valor:", value=f"R${float(product_price):.2f}", inline=False)
    embed.add_field(name="Steam:", value=steam_name, inline=False)

    from ui.views import ConfirmPurchaseView

    await interaction.response.send_message(embed=embed, view=ConfirmPurchaseView(product_id), ephemeral=True)


async def handle_purchase_confirm(interaction: discord.Interaction, product_id: int) -> None:
    lock_key = (interaction.user.id, product_id)
    if lock_key in _processing:
        await interaction.response.send_message("⏳ Já estamos processando, aguarde.", ephemeral=True)
        return

    _processing.add(lock_key)
    try:
        await _handle_purchase_confirm(interaction, product_id)
    finally:
        _processing.discard(lock_key)


async def _handle_purchase_confirm(interaction: discord.Interaction, product_id: int) -> None:
    # Remove os botões da própria mensagem IMEDIATAMENTE — segunda camada de
    # defesa contra clique duplicado (mesmo que o _processing lock de algum
    # jeito não pegasse, não tem mais botão pra clicar de novo).
    await interaction.response.edit_message(content="⏳ Processando sua compra...", embed=None, view=None)

    user = await get_linked_user(interaction.user.id)

    async with get_session() as session:
        product = await session.get(Product, product_id)
        if product is None or not product.is_active:
            await interaction.followup.send("⚠ Este produto não está mais disponível.", ephemeral=True)
            return

        if user is None:
            await interaction.followup.send("⚠ Steam não vinculada. Vincule antes de comprar.", ephemeral=True)
            return

        # revalida duplicidade — pode ter mudado entre a tela de confirmação e agora
        pending_result = await session.execute(
            select(Purchase).where(
                Purchase.discord_id == interaction.user.id,
                Purchase.product_id == product_id,
                Purchase.status == PurchaseStatus.pendente,
            )
        )
        if pending_result.scalar_one_or_none():
            await interaction.followup.send("ℹ Você já tem uma compra pendente desse produto.", ephemeral=True)
            return

        purchase = Purchase(
            discord_id=interaction.user.id,
            steam_id=user.steam_id,
            user_id=user.id,
            product_id=product.id,
            price=product.price,
            status=PurchaseStatus.pendente,
        )
        session.add(purchase)
        await session.commit()
        await session.refresh(purchase)

        product_name = product.name
        product_price = float(product.price)
        steam_name = user.steam_name
        steam_id = user.steam_id

    logger.info(
        "Nova compra: pedido #%s — usuário=%s (discord_id=%s) — produto='%s' — valor=R$%.2f",
        purchase.id, steam_name, interaction.user.id, product_name, product_price,
    )

    await log_purchase_event(
        interaction.client,
        title="🛒 NOVA COMPRA",
        description=(
            f"**Usuário:**\n{steam_name}\n\n"
            f"**Produto:**\n{product_name}\n\n"
            f"**Valor:**\nR${product_price:.2f}\n\n"
            f"**SteamID:**\n{steam_id}\n\n"
            f"**Status:**\n{purchase.status.value}"
        ),
        color=discord.Color.gold(),
    )

    channel = await ensure_purchase_channel(purchase=purchase, product=product, member=interaction.user)
    extra = f"\n\nAcompanhe o atendimento em {channel.mention}." if channel else ""

    if channel:
        async with get_session() as session:
            db_purchase = await session.get(Purchase, purchase.id)
            if db_purchase:
                db_purchase.support_channel_id = channel.id
                await session.commit()

    await interaction.followup.send(
        f"✅ Pedido **#{purchase.id}** registrado como **PENDENTE**.\n"
        f"Nesta etapa do projeto a confirmação de pagamento ainda é manual, feita por um administrador.{extra}",
        ephemeral=True,
    )


async def handle_purchase_cancel(interaction: discord.Interaction, product_id: int) -> None:
    await interaction.response.edit_message(content="❌ Compra cancelada.", embed=None, view=None)


# ---------------------------------------------------------------------------
# Transições de status — prontas pra Etapa 7 (pagamento/entrega) chamar.
# Nada aciona essas funções ainda nesta etapa.
# ---------------------------------------------------------------------------
async def mark_paid(purchase_id: int, *, payment_method: str | None = None, transaction_id: str | None = None) -> Purchase | None:
    """Pronta pra Etapa 7 chamar depois de confirmar o pagamento (manual ou
    via gateway). `payment_method`/`transaction_id` já ficam salvos quando
    informados, mas nada nesta etapa os preenche ainda."""

    async with get_session() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase is None:
            return None
        purchase.status = PurchaseStatus.pago
        purchase.paid_at = datetime.now(timezone.utc)
        if payment_method:
            purchase.payment_method = payment_method
        if transaction_id:
            purchase.payment_transaction_id = transaction_id
        await session.commit()
        await session.refresh(purchase)

    logger.info("Pedido #%s marcado como PAGO.", purchase_id)
    return purchase


async def mark_delivered(purchase_id: int) -> Purchase | None:
    async with get_session() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase is None:
            return None
        purchase.status = PurchaseStatus.entregue
        await session.commit()
        await session.refresh(purchase)

    logger.info("Pedido #%s marcado como ENTREGUE.", purchase_id)
    return purchase


async def mark_cancelled(purchase_id: int) -> Purchase | None:
    async with get_session() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase is None:
            return None
        if purchase.status == PurchaseStatus.entregue:
            # Uma vez ENTREGUE, o pedido é histórico — cancelar aqui zeraria
            # uma entrega que já aconteceu de verdade no jogo. Se for
            # necessário estornar, isso é uma ação administrativa separada
            # (fora do escopo desta etapa), não um simples cancelamento.
            logger.warning("Tentativa de cancelar pedido #%s que já está ENTREGUE — bloqueado.", purchase_id)
            return None
        purchase.status = PurchaseStatus.cancelado
        await session.commit()
        await session.refresh(purchase)

    logger.info("Pedido #%s marcado como CANCELADO.", purchase_id)
    return purchase


async def get_purchase_by_id(purchase_id: int) -> Purchase | None:
    async with get_session() as session:
        return await session.get(Purchase, purchase_id)


async def register_persistent_approval_views(bot) -> None:
    """Chamado uma vez no startup (main.py) — re-registra o botão de
    aprovação de pagamento de todo pedido ainda PENDENTE, senão os cliques
    em canais de atendimento antigos param de responder após um restart."""

    from ui.views import PurchaseApprovalView

    async with get_session() as session:
        result = await session.execute(select(Purchase).where(Purchase.status == PurchaseStatus.pendente))
        pending = result.scalars().all()

    for purchase in pending:
        bot.add_view(PurchaseApprovalView(purchase.id))

    logger.info("%d view(s) persistente(s) de aprovação de pagamento registrada(s).", len(pending))


# ---------------------------------------------------------------------------
# Orquestração Etapa 7 — aprovação manual de pagamento pelo admin.
#
#   PENDENTE --[admin aprova]--> PAGO --[automático]--> Delivery criada (Pendente)
#   PENDENTE / PAGO --[admin cancela]--> CANCELADO
#
# Chamadas pelos botões de PurchaseApprovalView (ui/views.py).
# ---------------------------------------------------------------------------
async def approve_payment(bot, purchase_id: int, admin_discord_id: int) -> tuple[Purchase, "Delivery"] | None:
    from delivery.queue import create_delivery_for_purchase

    async with get_session() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase is None or purchase.status != PurchaseStatus.pendente:
            return None
        product = await session.get(Product, purchase.product_id)
        product_name, product_price, steam_id = product.name, float(purchase.price), purchase.steam_id

    updated_purchase = await mark_paid(purchase_id, payment_method="manual")
    delivery = await create_delivery_for_purchase(purchase_id)

    logger.info(
        "Pagamento do pedido #%s aprovado manualmente por discord_id=%s. Entrega #%s criada.",
        purchase_id, admin_discord_id, delivery.id if delivery else "?",
    )

    await log_purchase_event(
        bot,
        title="💳 PAGAMENTO APROVADO",
        description=(
            f"**Pedido:** #{purchase_id}\n"
            f"**Produto:** {product_name}\n"
            f"**Valor:** R${product_price:.2f}\n"
            f"**SteamID:** {steam_id}\n"
            f"**Aprovado por:** <@{admin_discord_id}>"
        ),
        color=discord.Color.green(),
    )

    if updated_purchase.support_channel_id:
        channel = bot.get_channel(updated_purchase.support_channel_id)
        if channel:
            try:
                await channel.send(
                    f"✅ Pagamento aprovado por <@{admin_discord_id}>! Pedido **#{purchase_id}** agora está **PAGO**.\n"
                    f"Sua entrega foi registrada na fila (status: Pendente) — acompanhe em `📦・entregas`."
                )
            except discord.HTTPException:
                pass

    return updated_purchase, delivery


async def cancel_purchase(bot, purchase_id: int, admin_discord_id: int) -> Purchase | None:
    purchase = await mark_cancelled(purchase_id)
    if purchase is None:
        return None

    logger.info("Pedido #%s cancelado por discord_id=%s.", purchase_id, admin_discord_id)

    await log_purchase_event(
        bot,
        title="🚫 PEDIDO CANCELADO",
        description=f"**Pedido:** #{purchase_id}\n**Cancelado por:** <@{admin_discord_id}>",
        color=discord.Color.red(),
    )

    if purchase.support_channel_id:
        channel = bot.get_channel(purchase.support_channel_id)
        if channel:
            try:
                await channel.send(f"🚫 Pedido **#{purchase_id}** foi cancelado por <@{admin_discord_id}>.")
            except discord.HTTPException:
                pass

    return purchase
