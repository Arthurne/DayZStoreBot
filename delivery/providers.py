"""
Arquitetura preparada para integrações futuras de entrega no servidor DayZ.

Nesta etapa, TODA entrega é processada manualmente por um administrador
(botões Processar/Entregue/Falhou em /entregas) — nenhum código aqui é
chamado de verdade ainda. Quando uma integração real entrar (RCON, API
própria, Mod DayZ ou Webhook), ela implementa `DeliveryProvider` e é
plugada em delivery/queue.py sem precisar mudar o resto do sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    success: bool
    detail: str


class DeliveryProvider(ABC):
    """Sem implementação concreta ainda. Candidatos previstos pelo spec:
    RCON DayZ, API própria, Mod DayZ, Webhook — cada um vira uma subclasse
    numa etapa futura."""

    @abstractmethod
    async def deliver(self, *, steam_id64: str, items: list[str]) -> DeliveryResult: ...


async def automatic_delivery_enabled() -> bool:
    """Sempre False nesta etapa — toda entrega passa pelo admin. Espelha
    payments.payment.automatic_payment_enabled() pelo mesmo motivo: dar a
    quem for construir um painel/relatório uma forma de perguntar 'isso já
    é automático?' sem conhecer os detalhes de implementação."""

    return False
