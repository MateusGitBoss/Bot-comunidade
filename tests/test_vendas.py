import json
from datetime import datetime

import httpx
import pytest

from bot.vendas import ClienteVendas, Compra, ErroVendas, formatar_compras


def cliente_com(handler) -> ClienteVendas:  # type: ignore[no-untyped-def]
    http = httpx.AsyncClient(
        base_url="http://vendas.teste",
        headers={"Authorization": "Bearer tk"},
        transport=httpx.MockTransport(handler),
    )
    return ClienteVendas(http)


async def test_envia_email_no_corpo_com_token_e_le_compras() -> None:
    recebido: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recebido["metodo"] = request.method
        recebido["url"] = str(request.url)
        recebido["auth"] = request.headers["Authorization"]
        recebido["corpo"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[
                {
                    "produto": "Curso Lojista Digital",
                    "status": "aprovada",
                    "plataforma": "hotmart",
                    "atualizado_em": "2026-10-08T14:30:00+00:00",
                }
            ],
        )

    compras = await cliente_com(handler).compras_do_email("ana@exemplo.com")

    assert recebido == {
        "metodo": "POST",
        "url": "http://vendas.teste/vendas/consulta-status",
        "auth": "Bearer tk",
        "corpo": {"email": "ana@exemplo.com"},
    }
    assert compras[0].produto == "Curso Lojista Digital"
    assert compras[0].atualizado_em.year == 2026


async def test_email_invalido() -> None:
    cliente = cliente_com(lambda r: httpx.Response(422, json={"detail": "x"}))
    with pytest.raises(ValueError):
        await cliente.compras_do_email("nao-e-email")


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_erro_da_api(status: int) -> None:
    cliente = cliente_com(lambda r: httpx.Response(status))
    with pytest.raises(ErroVendas):
        await cliente.compras_do_email("ana@exemplo.com")


async def test_falha_de_rede() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede", request=request)

    with pytest.raises(ErroVendas):
        await cliente_com(handler).compras_do_email("ana@exemplo.com")


def test_formatar_sem_compras() -> None:
    assert "Não encontrei compras" in formatar_compras([])


def test_formatar_traduz_status() -> None:
    texto = formatar_compras(
        [
            Compra("Curso A", "pendente", "kiwify", datetime(2026, 10, 8, 9, 5)),
            Compra("Curso B", "status-novo", "hotmart", datetime(2026, 10, 7, 18, 0)),
        ]
    )
    assert (
        "**Curso A**: ⏳ aguardando pagamento (atualizado em 08/10/2026 09:05, via kiwify)" in texto
    )
    # Status desconhecido aparece cru, em vez de quebrar
    assert "**Curso B**: status-novo" in texto
