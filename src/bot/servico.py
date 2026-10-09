"""Regras do bot, sem nada de Discord: dá para testar tudo sem abrir conexão com o Discord."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from bot.faq import BaseFaq
from bot.ia import RESPOSTA_ERRO, AssistenteFaq, ErroIA
from bot.limite import LimitadorUso
from bot.repositorio import Repositorio, ResumoUso, hash_usuario
from bot.vendas import ClienteVendas, ErroVendas, formatar_compras

log = logging.getLogger(__name__)

TAMANHO_MAXIMO_PERGUNTA = 500


@dataclass(frozen=True)
class ResultadoPergunta:
    texto: str
    respondida: bool
    # None quando nada foi gravado (limite estourado, erro): sem botão de feedback
    interacao_id: int | None = None
    encaminhar_para_humano: bool = False


class ServicoBot:
    def __init__(
        self,
        faq: BaseFaq,
        assistente: AssistenteFaq,
        repositorio: Repositorio,
        limitador: LimitadorUso,
        vendas: ClienteVendas,
        segredo_hash: str,
        trechos_por_pergunta: int = 3,
    ) -> None:
        self.faq = faq
        self.assistente = assistente
        self.repositorio = repositorio
        self.limitador = limitador
        self.vendas = vendas
        self.segredo_hash = segredo_hash
        self.trechos_por_pergunta = trechos_por_pergunta

    def _hash(self, usuario_id: int) -> str:
        return hash_usuario(usuario_id, self.segredo_hash)

    async def perguntar(self, usuario_id: int, pergunta: str) -> ResultadoPergunta:
        pergunta = pergunta.strip()[:TAMANHO_MAXIMO_PERGUNTA]
        usuario = self._hash(usuario_id)

        if not self.limitador.tentar(usuario):
            minutos = max(1, self.limitador.segundos_para_liberar(usuario) // 60)
            return ResultadoPergunta(
                texto=f"Você chegou ao limite de perguntas por hora. Tente em {minutos} min.",
                respondida=False,
            )

        trechos = self.faq.buscar(pergunta, limite=self.trechos_por_pergunta)
        try:
            resposta = await self.assistente.responder(pergunta, trechos)
        except ErroIA:
            log.exception("falha ao chamar a IA")
            return ResultadoPergunta(texto=RESPOSTA_ERRO, respondida=False)

        interacao_id = await self.repositorio.registrar_interacao(
            usuario, pergunta, resposta, self.assistente.modelo
        )
        log.info(
            "pergunta respondida" if resposta.respondida else "pergunta sem base",
            extra={
                "interacao_id": interacao_id,
                "trechos": resposta.trechos_usados,
                "custo_usd": str(resposta.custo_usd),
            },
        )
        return ResultadoPergunta(
            texto=resposta.texto,
            respondida=resposta.respondida,
            interacao_id=interacao_id,
            encaminhar_para_humano=not resposta.respondida,
        )

    async def feedback(self, interacao_id: int, usuario_id: int, util: bool) -> bool:
        return await self.repositorio.registrar_feedback(interacao_id, self._hash(usuario_id), util)

    async def status_compra(self, email: str) -> str:
        try:
            compras = await self.vendas.compras_do_email(email.strip())
        except ValueError:
            return "Esse e-mail não parece válido. Confira e tente de novo."
        except ErroVendas:
            log.exception("falha ao consultar a API de vendas")
            return "Não consegui consultar agora. Tente de novo em alguns minutos."
        return formatar_compras(compras)

    def recarregar_faq(self, faq: BaseFaq) -> int:
        self.faq = faq
        return len(faq.trechos)

    async def resumo_hoje(self, agora: datetime | None = None) -> ResumoUso:
        agora = agora or datetime.now(UTC)
        inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.repositorio.resumo_desde(inicio)
