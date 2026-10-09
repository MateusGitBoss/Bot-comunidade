from pathlib import Path

import anthropic
import httpx
import httpx2
import pytest

from bot.faq import BaseFaq, Trecho
from bot.ia import RESPOSTA_ERRO, RESPOSTA_SEM_BASE, AssistenteFaq
from bot.limite import LimitadorUso
from bot.repositorio import hash_usuario
from bot.servico import TAMANHO_MAXIMO_PERGUNTA, ServicoBot
from bot.vendas import ClienteVendas
from tests.fakes import ClienteFalso, RepositorioFalso, mensagem

FAQ = BaseFaq.carregar(Path(__file__).parent.parent / "docs" / "faq")
SEGREDO = "segredo-teste"


def montar(
    cliente: ClienteFalso,
    repositorio: RepositorioFalso | None = None,
    limite: int = 10,
    vendas_handler=None,  # type: ignore[no-untyped-def]
) -> ServicoBot:
    handler = vendas_handler or (lambda r: httpx.Response(200, json=[]))
    vendas = ClienteVendas(
        httpx.AsyncClient(base_url="http://vendas", transport=httpx.MockTransport(handler))
    )
    return ServicoBot(
        faq=FAQ,
        assistente=AssistenteFaq(cliente.como_anthropic(), "prompt", "claude-haiku-5-5"),
        repositorio=repositorio or RepositorioFalso(),
        limitador=LimitadorUso(maximo=limite),
        vendas=vendas,
        segredo_hash=SEGREDO,
    )


async def test_pergunta_respondida_e_gravada_sem_id_do_discord() -> None:
    repositorio = RepositorioFalso()
    cliente = ClienteFalso(mensagem({"respondida": True, "resposta": "Você tem 7 dias."}))
    servico = montar(cliente, repositorio)

    resultado = await servico.perguntar(123456789, "posso pedir reembolso?")

    assert resultado.texto == "Você tem 7 dias."
    assert resultado.interacao_id == 1
    assert not resultado.encaminhar_para_humano
    gravada = repositorio.interacoes[0]
    assert gravada["usuario_hash"] == hash_usuario(123456789, SEGREDO)
    assert "123456789" not in gravada["usuario_hash"]


async def test_pergunta_sem_base_e_encaminhada_e_tambem_gravada() -> None:
    repositorio = RepositorioFalso()
    cliente = ClienteFalso()
    resultado = await montar(cliente, repositorio).perguntar(1, "qual a capital da Mongólia?")

    assert resultado.texto == RESPOSTA_SEM_BASE
    assert resultado.encaminhar_para_humano
    # Pergunta sem resposta é gravada: é assim que se descobre o que falta na FAQ
    assert len(repositorio.interacoes) == 1
    assert cliente.chamadas == []


async def test_limite_por_usuario() -> None:
    cliente = ClienteFalso(mensagem({"respondida": True, "resposta": "ok"}))
    servico = montar(cliente, limite=1)

    await servico.perguntar(1, "posso parcelar?")
    bloqueado = await servico.perguntar(1, "posso parcelar?")

    assert "limite de perguntas por hora" in bloqueado.texto
    assert bloqueado.interacao_id is None
    assert len(cliente.chamadas) == 1


async def test_erro_da_ia_nao_grava_e_avisa() -> None:
    repositorio = RepositorioFalso()
    requisicao = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    cliente = ClienteFalso(anthropic.APIConnectionError(request=requisicao))
    resultado = await montar(cliente, repositorio).perguntar(1, "posso parcelar?")
    assert resultado.texto == RESPOSTA_ERRO
    assert repositorio.interacoes == []


async def test_pergunta_gigante_e_cortada() -> None:
    repositorio = RepositorioFalso()
    cliente = ClienteFalso(mensagem({"respondida": True, "resposta": "ok"}))
    await montar(cliente, repositorio).perguntar(1, "parcelar " * 500)
    assert len(repositorio.interacoes[0]["pergunta"]) <= TAMANHO_MAXIMO_PERGUNTA


async def test_feedback_so_de_quem_perguntou() -> None:
    repositorio = RepositorioFalso()
    cliente = ClienteFalso(mensagem({"respondida": True, "resposta": "ok"}))
    servico = montar(cliente, repositorio)
    resultado = await servico.perguntar(1, "posso parcelar?")
    assert resultado.interacao_id is not None

    assert not await servico.feedback(resultado.interacao_id, usuario_id=2, util=False)
    assert await servico.feedback(resultado.interacao_id, usuario_id=1, util=True)
    assert repositorio.interacoes[0]["util"] is True


@pytest.mark.parametrize(
    ("resposta", "esperado"),
    [
        (httpx.Response(200, json=[]), "Não encontrei compras"),
        (httpx.Response(422), "não parece válido"),
        (httpx.Response(500), "Não consegui consultar"),
    ],
)
async def test_status_compra(resposta: httpx.Response, esperado: str) -> None:
    servico = montar(ClienteFalso(), vendas_handler=lambda r: resposta)
    assert esperado in await servico.status_compra(" ana@exemplo.com ")


def test_recarregar_faq() -> None:
    servico = montar(ClienteFalso())
    nova = BaseFaq([Trecho("a.md", "T", "texto")])
    assert servico.recarregar_faq(nova) == 1
    assert servico.faq is nova
