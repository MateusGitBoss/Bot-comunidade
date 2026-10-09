"""Dublês de teste: substituem a API do Claude e o banco sem rede nem custo."""

import json
from typing import Any, cast

import anthropic
from anthropic.types import Message


def mensagem(
    texto: str | dict[str, Any],
    stop_reason: str = "end_turn",
    entrada: int = 500,
    saida: int = 80,
) -> Message:
    corpo = texto if isinstance(texto, str) else json.dumps(texto, ensure_ascii=False)
    return Message.model_validate(
        {
            "id": "msg_teste",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": corpo}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": entrada, "output_tokens": saida},
        }
    )


class _MensagensFalsas:
    def __init__(self, respostas: list[Message | Exception]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class ClienteFalso:
    """Imita anthropic.AsyncAnthropic: guarda o que foi enviado e devolve respostas prontas."""

    def __init__(self, *respostas: Message | Exception) -> None:
        self.messages = _MensagensFalsas(list(respostas))

    @property
    def chamadas(self) -> list[dict[str, Any]]:
        return self.messages.chamadas

    def como_anthropic(self) -> anthropic.AsyncAnthropic:
        return cast(anthropic.AsyncAnthropic, self)


class RepositorioFalso:
    """Guarda as interações numa lista, no lugar do Postgres."""

    def __init__(self) -> None:
        self.interacoes: list[dict[str, Any]] = []

    async def registrar_interacao(
        self, usuario_hash: str, pergunta: str, resposta: Any, modelo: str
    ) -> int:
        self.interacoes.append(
            {"usuario_hash": usuario_hash, "pergunta": pergunta, "resposta": resposta, "util": None}
        )
        return len(self.interacoes)

    async def registrar_feedback(self, interacao_id: int, usuario_hash: str, util: bool) -> bool:
        if not 1 <= interacao_id <= len(self.interacoes):
            return False
        interacao = self.interacoes[interacao_id - 1]
        if interacao["usuario_hash"] != usuario_hash:
            return False
        interacao["util"] = util
        return True

    async def resumo_desde(self, inicio: Any) -> Any:
        raise NotImplementedError
