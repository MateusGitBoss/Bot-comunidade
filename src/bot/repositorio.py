"""Acesso ao Postgres com SQL escrito à mão (psycopg 3, assíncrono, com pool de conexões)."""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from importlib import resources
from typing import Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from bot.ia import RespostaIA

log = logging.getLogger(__name__)


def hash_usuario(usuario_id: int | str, segredo: str) -> str:
    """HMAC-SHA256: sem o segredo, não dá para voltar do hash para o ID do Discord."""
    return hmac.new(segredo.encode(), str(usuario_id).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ResumoUso:
    perguntas: int
    respondidas: int
    uteis: int
    nao_uteis: int
    custo_usd: Decimal


class Repositorio(Protocol):
    async def registrar_interacao(
        self, usuario_hash: str, pergunta: str, resposta: RespostaIA, modelo: str
    ) -> int: ...

    async def registrar_feedback(
        self, interacao_id: int, usuario_hash: str, util: bool
    ) -> bool: ...

    async def resumo_desde(self, inicio: datetime) -> ResumoUso: ...


class RepositorioPostgres:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    @classmethod
    async def abrir(cls, database_url: str) -> "RepositorioPostgres":
        pool = AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False)
        await pool.open(wait=True)
        return cls(pool)

    async def fechar(self) -> None:
        await self.pool.close()

    async def migrar(self) -> list[str]:
        """Aplica os .sql de migrations/ ainda não aplicados, cada um numa transação."""
        novas: list[str] = []
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    versao TEXT PRIMARY KEY,
                    aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor = await conn.execute("SELECT versao FROM schema_migrations")
            aplicadas = {linha[0] for linha in await cursor.fetchall()}
            pasta = resources.files("bot") / "migrations"
            arquivos = sorted(
                (p for p in pasta.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name
            )
            for arquivo in arquivos:
                if arquivo.name in aplicadas:
                    continue
                async with conn.transaction():
                    await conn.execute(arquivo.read_text(encoding="utf-8"))
                    await conn.execute(
                        "INSERT INTO schema_migrations (versao) VALUES (%s)", (arquivo.name,)
                    )
                log.info("migração aplicada", extra={"versao": arquivo.name})
                novas.append(arquivo.name)
        return novas

    async def registrar_interacao(
        self, usuario_hash: str, pergunta: str, resposta: RespostaIA, modelo: str
    ) -> int:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO interacoes (
                    usuario_hash, pergunta, resposta, respondida, trechos_usados,
                    tokens_entrada, tokens_saida, custo_usd, modelo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    usuario_hash,
                    pergunta,
                    resposta.texto,
                    resposta.respondida,
                    resposta.trechos_usados,
                    resposta.tokens_entrada,
                    resposta.tokens_saida,
                    resposta.custo_usd,
                    modelo,
                ),
            )
            linha = await cursor.fetchone()
            assert linha is not None
            return int(linha[0])

    async def registrar_feedback(self, interacao_id: int, usuario_hash: str, util: bool) -> bool:
        """Só quem perguntou pode avaliar a resposta. Devolve False se não achou a interação."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                "UPDATE interacoes SET util = %s WHERE id = %s AND usuario_hash = %s",
                (util, interacao_id, usuario_hash),
            )
            return cursor.rowcount == 1

    async def resumo_desde(self, inicio: datetime) -> ResumoUso:
        async with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT count(*)                                AS perguntas,
                       count(*) FILTER (WHERE respondida)      AS respondidas,
                       count(*) FILTER (WHERE util)            AS uteis,
                       count(*) FILTER (WHERE util = false)    AS nao_uteis,
                       coalesce(sum(custo_usd), 0)             AS custo_usd
                FROM interacoes
                WHERE criado_em >= %s
                """,
                (inicio,),
            )
            linha = await cursor.fetchone()
            assert linha is not None
            return ResumoUso(**linha)
