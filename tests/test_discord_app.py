"""A camada do Discord é testada com interações falsas: nenhum acesso à rede."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import pytest
from discord import app_commands

from bot.discord_app import BotComunidade, ViewFeedback, registrar_comandos
from bot.faq import BaseFaq
from bot.ia import AssistenteFaq
from bot.limite import LimitadorUso
from bot.servico import ServicoBot
from bot.vendas import ClienteVendas
from tests.fakes import ClienteFalso, RepositorioFalso, mensagem

FAQ_DIR = Path(__file__).parent.parent / "docs" / "faq"
CANAL_SUPORTE = 999


def servico_com(cliente: ClienteFalso, repositorio: RepositorioFalso | None = None) -> ServicoBot:
    vendas = ClienteVendas(
        httpx.AsyncClient(
            base_url="http://vendas",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
        )
    )
    return ServicoBot(
        faq=BaseFaq.carregar(FAQ_DIR),
        assistente=AssistenteFaq(cliente.como_anthropic(), "prompt", "claude-haiku-5-5"),
        repositorio=repositorio or RepositorioFalso(),
        limitador=LimitadorUso(maximo=10),
        vendas=vendas,
        segredo_hash="s",
    )


def interacao(usuario_id: int = 1, canal: Any = None) -> Any:
    cliente = SimpleNamespace(latency=0.042, get_channel=MagicMock(return_value=canal))
    return SimpleNamespace(
        user=SimpleNamespace(id=usuario_id, mention=f"<@{usuario_id}>"),
        client=cliente,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def arvore(servico: ServicoBot) -> app_commands.CommandTree[discord.Client]:
    bot = BotComunidade(guild_id=None)
    registrar_comandos(bot.tree, servico, lambda: BaseFaq.carregar(FAQ_DIR), CANAL_SUPORTE)
    return bot.tree


async def executar(tree: Any, nome: str, inter: Any, **parametros: Any) -> None:
    comando = tree.get_command(nome)
    assert comando is not None, nome
    await comando.callback(inter, **parametros)


def test_comandos_registrados() -> None:
    tree = arvore(servico_com(ClienteFalso()))
    nomes = {c.name for c in tree.get_commands()}
    assert nomes == {"ping", "pergunta", "status-compra", "faq-recarregar", "uso-hoje"}


def test_comandos_de_admin_exigem_permissao() -> None:
    tree = arvore(servico_com(ClienteFalso()))
    for nome in ("faq-recarregar", "uso-hoje"):
        comando = tree.get_command(nome)
        assert comando is not None and comando.default_permissions is not None
        assert comando.default_permissions.manage_guild


async def test_ping() -> None:
    inter = interacao()
    await executar(arvore(servico_com(ClienteFalso())), "ping", inter)
    inter.response.send_message.assert_awaited_once_with("pong (42 ms)", ephemeral=True)


async def test_pergunta_respondida_vem_com_botoes_de_feedback() -> None:
    cliente = ClienteFalso(mensagem({"respondida": True, "resposta": "Em até 12 vezes."}))
    inter = interacao()
    await executar(arvore(servico_com(cliente)), "pergunta", inter, texto="posso parcelar?")

    inter.response.defer.assert_awaited_once_with(thinking=True)
    args, kwargs = inter.followup.send.await_args
    assert args[0] == "> posso parcelar?\nEm até 12 vezes."
    assert isinstance(kwargs["view"], ViewFeedback)


async def test_pergunta_sem_base_vai_para_o_canal_de_suporte() -> None:
    canal = MagicMock(spec=discord.TextChannel)
    canal.send = AsyncMock()
    inter = interacao(usuario_id=7, canal=canal)
    await executar(
        arvore(servico_com(ClienteFalso())), "pergunta", inter, texto="capital da Mongólia?"
    )

    _, kwargs = inter.followup.send.await_args
    assert "view" not in kwargs
    inter.client.get_channel.assert_called_once_with(CANAL_SUPORTE)
    assert "<@7>" in canal.send.await_args.args[0]


async def test_status_compra_e_efemero() -> None:
    inter = interacao()
    await executar(arvore(servico_com(ClienteFalso())), "status-compra", inter, email="a@b.com")
    inter.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert inter.followup.send.await_args.kwargs == {"ephemeral": True}


async def test_faq_recarregar() -> None:
    inter = interacao()
    await executar(arvore(servico_com(ClienteFalso())), "faq-recarregar", inter)
    texto = inter.response.send_message.await_args.args[0]
    assert texto.startswith("FAQ recarregada:")


async def test_faq_recarregar_com_erro_nao_derruba_o_bot(tmp_path: Path) -> None:
    bot = BotComunidade(guild_id=None)
    registrar_comandos(
        bot.tree, servico_com(ClienteFalso()), lambda: BaseFaq.carregar(tmp_path), None
    )
    inter = interacao()
    await executar(bot.tree, "faq-recarregar", inter)
    assert inter.response.send_message.await_args.args[0].startswith("Falhou")


async def test_uso_hoje() -> None:
    servico = servico_com(ClienteFalso())
    servico.repositorio = MagicMock()
    servico.repositorio.resumo_desde = AsyncMock(
        return_value=SimpleNamespace(
            perguntas=5, respondidas=4, uteis=3, nao_uteis=1, custo_usd=0.0012
        )
    )
    inter = interacao()
    await executar(arvore(servico), "uso-hoje", inter)
    texto = inter.response.send_message.await_args.args[0]
    assert "5 perguntas" in texto and "US$ 0.0012" in texto


@pytest.mark.parametrize(("usuario", "esperado"), [(1, "Obrigado"), (2, "Só quem fez")])
async def test_feedback_pelos_botoes(usuario: int, esperado: str) -> None:
    repositorio = RepositorioFalso()
    servico = servico_com(
        ClienteFalso(mensagem({"respondida": True, "resposta": "ok"})), repositorio
    )
    resultado = await servico.perguntar(1, "posso parcelar?")
    assert resultado.interacao_id is not None

    view = ViewFeedback(servico, resultado.interacao_id)
    inter = interacao(usuario_id=usuario)
    await view._registrar(inter, util=True)
    assert inter.response.send_message.await_args.args[0].startswith(esperado)


async def test_resumo_hoje_comeca_a_meia_noite() -> None:
    servico = servico_com(ClienteFalso())
    servico.repositorio = MagicMock()
    servico.repositorio.resumo_desde = AsyncMock()
    await servico.resumo_hoje(datetime(2026, 10, 9, 15, 30, tzinfo=UTC))
    servico.repositorio.resumo_desde.assert_awaited_once_with(datetime(2026, 10, 9, tzinfo=UTC))
