"""Testes contra um Postgres de verdade (DATABASE_URL_TESTE). No CI, um service container."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from bot.ia import RespostaIA
from bot.repositorio import RepositorioPostgres, hash_usuario

URL = os.environ.get("DATABASE_URL_TESTE")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL_TESTE não definida")


@pytest.fixture
async def repo() -> AsyncIterator[RepositorioPostgres]:
    assert URL
    repositorio = await RepositorioPostgres.abrir(URL)
    async with repositorio.pool.connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS interacoes, schema_migrations")
    await repositorio.migrar()
    yield repositorio
    await repositorio.fechar()


RESPOSTA = RespostaIA(
    texto="Você tem 7 dias.",
    respondida=True,
    trechos_usados=["reembolso.md#Posso pedir reembolso?"],
    tokens_entrada=600,
    tokens_saida=40,
    custo_usd=Decimal("0.00008"),
)


async def test_migrar_e_idempotente(repo: RepositorioPostgres) -> None:
    assert await repo.migrar() == []


async def test_registra_interacao_e_feedback(repo: RepositorioPostgres) -> None:
    usuario = hash_usuario(42, "s")
    interacao_id = await repo.registrar_interacao(
        usuario, "reembolso?", RESPOSTA, "claude-haiku-5-5"
    )

    assert await repo.registrar_feedback(interacao_id, usuario, util=True)
    # Outro usuário não pode avaliar a resposta de alguém
    assert not await repo.registrar_feedback(interacao_id, hash_usuario(43, "s"), util=False)
    assert not await repo.registrar_feedback(999_999, usuario, util=False)

    async with repo.pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT util, trechos_usados, custo_usd, modelo FROM interacoes WHERE id = %s",
            (interacao_id,),
        )
        linha = await cursor.fetchone()
    assert linha == (
        True,
        ["reembolso.md#Posso pedir reembolso?"],
        Decimal("0.000080"),
        "claude-haiku-5-5",
    )


async def test_resumo(repo: RepositorioPostgres) -> None:
    inicio = datetime.now(UTC) - timedelta(minutes=1)
    sem_base = RespostaIA(texto="encaminhado", respondida=False)
    a = await repo.registrar_interacao("u1", "p1", RESPOSTA, "claude-haiku-5-5")
    b = await repo.registrar_interacao("u2", "p2", RESPOSTA, "claude-haiku-5-5")
    await repo.registrar_interacao("u3", "p3", sem_base, "claude-haiku-5-5")
    await repo.registrar_feedback(a, "u1", True)
    await repo.registrar_feedback(b, "u2", False)

    resumo = await repo.resumo_desde(inicio)

    assert (resumo.perguntas, resumo.respondidas, resumo.uteis, resumo.nao_uteis) == (3, 2, 1, 1)
    assert resumo.custo_usd == Decimal("0.00016")
