"""
Formulário de produto (criar/editar).

Discord permite no máximo 5 TextInput por Modal, e o produto tem 6 campos
(Nome, Descrição, Preço, Categoria, Itens, Imagem). Por isso o formulário é
dividido em dois modais encadeados: o segundo abre automaticamente ao
confirmar o primeiro (`interaction.response.send_modal()` dentro do
`on_submit` do primeiro). O produto só é criado/atualizado depois do
segundo — se o usuário fechar o segundo modal sem enviar, nada é salvo.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

import discord

logger = logging.getLogger(__name__)

OnComplete = Callable[[discord.Interaction, dict], Awaitable[None]]


class ProductModalStep2(discord.ui.Modal):
    def __init__(self, *, step1_data: dict, on_complete: OnComplete, defaults: dict | None = None):
        super().__init__(title="Criar Produto (2/2)")
        self._step1_data = step1_data
        self._on_complete = on_complete

        self.items_input = discord.ui.TextInput(
            label="Itens da entrega (um por linha)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            default="\n".join(defaults.get("items", [])) if defaults else None,
        )
        self.image_url = discord.ui.TextInput(
            label="Imagem (URL)",
            required=False,
            max_length=500,
            placeholder="https://... (opcional)",
            default=defaults.get("image_url") if defaults else None,
        )
        self.add_item(self.items_input)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        items = [line.strip() for line in str(self.items_input.value or "").splitlines() if line.strip()]
        image_url = str(self.image_url.value or "").strip() or None

        full_data = {**self._step1_data, "items": items, "image_url": image_url}

        # Deferir JÁ, antes de chamar on_complete: criar categoria/canal e
        # postar a mensagem de venda no Discord envolve várias chamadas
        # sequenciais à API e facilmente passa dos 3s que o Discord dá pra
        # responder a uma interação. Sem isso, a interação "falha" no
        # cliente (This interaction failed) mesmo quando o produto acaba
        # sendo criado por trás — e, pior, sem nenhum aviso claro do erro.
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await self._on_complete(interaction, full_data)
        except Exception:
            logger.exception("Erro ao salvar produto (nome='%s')", full_data.get("name"))
            await interaction.followup.send(
                "⚠ Ocorreu um erro ao salvar o produto. Verifique os logs do bot e tente novamente.",
                ephemeral=True,
            )


class ProductModalStep1(discord.ui.Modal):
    def __init__(self, *, on_complete: OnComplete, defaults: dict | None = None, editing: bool = False):
        super().__init__(title=f"{'Editar' if editing else 'Criar'} Produto (1/2)")
        self._on_complete = on_complete
        self._defaults = defaults

        self.name = discord.ui.TextInput(
            label="Nome", max_length=100, default=defaults.get("name") if defaults else None
        )
        self.description = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            default=defaults.get("description") if defaults else None,
        )
        self.price = discord.ui.TextInput(
            label="Preço (ex: 29.90)",
            max_length=20,
            placeholder="29.90",
            default=str(defaults["price"]) if defaults else None,
        )
        self.category = discord.ui.TextInput(
            label="Categoria",
            max_length=50,
            placeholder="Armas, Kits, VIP, Veículos...",
            default=defaults.get("category") if defaults else None,
        )
        for item in (self.name, self.description, self.price, self.category):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_value = float(str(self.price.value).replace(",", "."))
        except ValueError:
            await interaction.response.send_message(
                "⚠ Preço inválido. Use um número, ex: `29.90`.", ephemeral=True
            )
            return

        if price_value <= 0:
            await interaction.response.send_message(
                "⚠ O preço precisa ser maior que zero.", ephemeral=True
            )
            return

        step1_data = {
            "name": str(self.name.value).strip(),
            "description": str(self.description.value or "").strip(),
            "price": price_value,
            "category": str(self.category.value).strip(),
        }

        step2 = ProductModalStep2(step1_data=step1_data, on_complete=self._on_complete, defaults=self._defaults)
        await interaction.response.send_modal(step2)


async def start_product_modal(
    interaction: discord.Interaction, *, on_complete: OnComplete, defaults: dict | None = None, editing: bool = False
) -> None:
    """Ponto de entrada único usado pelos comandos — abre o primeiro dos
    dois modais encadeados. `defaults` é usado por /produto editar pra
    pré-preencher os campos com os valores atuais do produto."""

    modal = ProductModalStep1(on_complete=on_complete, defaults=defaults, editing=editing)
    await interaction.response.send_modal(modal)
