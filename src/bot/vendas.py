"""Cliente da API do webhook-vendas (P2): consulta o status das compras de um e-mail."""

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

# Tradução dos status internos do P2 para o aluno
STATUS_LEGIVEL = {
    "aprovada": "✅ aprovada",
    "pendente": "⏳ aguardando pagamento",
    "recusada": "❌ pagamento recusado",
    "cancelada": "❌ cancelada",
    "reembolsada": "↩️ reembolsada",
    "chargeback": "⚠️ contestada no cartão",
}


class ErroVendas(Exception):
    """A API de vendas não respondeu como esperado."""


@dataclass(frozen=True)
class Compra:
    produto: str
    status: str
    plataforma: str
    atualizado_em: datetime


class ClienteVendas:
    def __init__(self, cliente_http: httpx.AsyncClient) -> None:
        self.http = cliente_http

    @classmethod
    def criar(cls, base_url: str, token: str, timeout: float = 10) -> "ClienteVendas":
        return cls(
            httpx.AsyncClient(
                base_url=base_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
        )

    async def fechar(self) -> None:
        await self.http.aclose()

    async def compras_do_email(self, email: str) -> list[Compra]:
        # POST com o e-mail no corpo: e-mail na URL acabaria nos logs de acesso
        try:
            resposta = await self.http.post("/vendas/consulta-status", json={"email": email})
        except httpx.HTTPError as erro:
            raise ErroVendas(f"falha de rede: {erro.__class__.__name__}") from erro
        if resposta.status_code == 422:
            raise ValueError("e-mail inválido")
        if resposta.status_code != 200:
            log.warning("API de vendas respondeu erro", extra={"status": resposta.status_code})
            raise ErroVendas(f"status {resposta.status_code}")
        return [
            Compra(
                produto=item["produto"],
                status=item["status"],
                plataforma=item["plataforma"],
                atualizado_em=datetime.fromisoformat(item["atualizado_em"]),
            )
            for item in resposta.json()
        ]


def formatar_compras(compras: list[Compra]) -> str:
    if not compras:
        return (
            "Não encontrei compras com esse e-mail. Confira se é o mesmo e-mail usado no "
            "pagamento. Compras no boleto só aparecem depois que o boleto é gerado."
        )
    linhas = ["Suas compras:"]
    for c in compras:
        status = STATUS_LEGIVEL.get(c.status, c.status)
        quando = c.atualizado_em.strftime("%d/%m/%Y %H:%M")
        linhas.append(f"• **{c.produto}**: {status} (atualizado em {quando}, via {c.plataforma})")
    return "\n".join(linhas)
