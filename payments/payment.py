"""
Abstração de pagamento.

Nesta etapa NÃO existe pagamento automático — toda confirmação é manual
(um administrador confirma "na mão" que recebeu o PIX; ainda nem existe
comando pra isso). Este arquivo só define o contrato que a implementação
real (PIX/Mercado Pago/API própria) vai seguir na próxima etapa, pra quem
for integrar não precisar mexer em store/purchases.py depois — só plugar
um PaymentProvider concreto aqui.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PaymentCharge:
    reference: str
    checkout_url: str | None = None
    qr_code: str | None = None


@dataclass
class PaymentStatus:
    reference: str
    approved: bool


class PaymentProvider(ABC):
    """Sem implementação concreta ainda — ver payments/ na Etapa 7."""

    @abstractmethod
    async def create_charge(self, *, amount: float, description: str, reference: str) -> PaymentCharge: ...

    @abstractmethod
    async def check_status(self, reference: str) -> PaymentStatus: ...


async def automatic_payment_enabled() -> bool:
    """Sempre False nesta etapa. Usado por quem precisar decidir entre
    mostrar 'confirme manualmente' ou 'aguardando confirmação automática'
    (ex: um /painel futuro) sem precisar saber os detalhes de implementação."""

    return False
