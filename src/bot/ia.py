"""Chamada ao Claude: monta o prompt com os trechos da FAQ e interpreta a resposta.

Esta é a parte "RAG simples": Recuperar (faq.buscar) -> Aumentar o prompt com os trechos ->
Gerar a resposta. O modelo só pode usar o que veio nos trechos; se não der, devolve
respondida=false e a pergunta vai para uma pessoa.
"""

import json
import logging
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import anthropic

from bot.faq import TrechoEncontrado

log = logging.getLogger(__name__)

# Preço em US$ por milhão de tokens (entrada, saída). Conferir na página de preços da Anthropic
# quando trocar de modelo: o custo estimado gravado no banco depende desta tabela.
PRECOS_POR_MILHAO: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("3"), Decimal("15")),
}

RESPOSTA_SEM_BASE = (
    "Não encontrei isso na nossa base de dúvidas. Vou encaminhar sua pergunta para a equipe, "
    "que responde no canal de suporte."
)
RESPOSTA_ERRO = "Tive um problema para responder agora. Tente de novo em alguns minutos."

# Formato de saída garantido pela API (structured outputs): sempre JSON válido neste esquema,
# então não dependemos de "responda só com JSON" no texto do prompt.
ESQUEMA_RESPOSTA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "respondida": {"type": "boolean"},
        "resposta": {"type": "string"},
    },
    "required": ["respondida", "resposta"],
    "additionalProperties": False,
}


class ErroIA(Exception):
    """Falha ao falar com a API (rede, limite, indisponibilidade). Não é culpa do usuário."""


@dataclass(frozen=True)
class RespostaIA:
    texto: str
    respondida: bool
    trechos_usados: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: Decimal = Decimal(0)


def estimar_custo(modelo: str, tokens_entrada: int, tokens_saida: int) -> Decimal:
    if modelo not in PRECOS_POR_MILHAO:
        log.warning("modelo sem preço cadastrado, custo gravado como 0", extra={"modelo": modelo})
        return Decimal(0)
    preco_entrada, preco_saida = PRECOS_POR_MILHAO[modelo]
    return (tokens_entrada * preco_entrada + tokens_saida * preco_saida) / 1_000_000


def limpar_pergunta(pergunta: str) -> str:
    """Tira < e > para o aluno não conseguir fechar a tag <pergunta> e se passar por FAQ."""
    return pergunta.replace("<", "").replace(">", "").strip()


def montar_conteudo(pergunta: str, trechos: list[TrechoEncontrado]) -> str:
    blocos = "\n".join(
        f'<trecho titulo="{t.trecho.titulo}">\n{t.trecho.texto}\n</trecho>' for t in trechos
    )
    return f"<faq>\n{blocos}\n</faq>\n\n<pergunta>\n{limpar_pergunta(pergunta)}\n</pergunta>"


class AssistenteFaq:
    def __init__(
        self,
        cliente: anthropic.AsyncAnthropic,
        prompt_sistema: str,
        modelo: str,
        max_tokens: int = 1024,
    ) -> None:
        self.cliente = cliente
        self.prompt_sistema = prompt_sistema
        self.modelo = modelo
        self.max_tokens = max_tokens

    @classmethod
    def com_prompt_de_arquivo(
        cls, cliente: anthropic.AsyncAnthropic, caminho: Path, modelo: str, max_tokens: int
    ) -> "AssistenteFaq":
        # O prompt fica versionado em arquivo: muda por PR, com histórico, sem mexer no código
        return cls(cliente, caminho.read_text(encoding="utf-8"), modelo, max_tokens)

    async def responder(self, pergunta: str, trechos: list[TrechoEncontrado]) -> RespostaIA:
        if not trechos:
            # Sem base relevante não vale pagar a chamada: a resposta seria "não sei" de todo jeito
            return RespostaIA(texto=RESPOSTA_SEM_BASE, respondida=False)

        try:
            resposta = await self.cliente.messages.create(
                model=self.modelo,
                max_tokens=self.max_tokens,
                system=self.prompt_sistema,
                messages=[{"role": "user", "content": montar_conteudo(pergunta, trechos)}],
                # effort baixo: a tarefa é reescrever um trecho curto, não raciocinar muito
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": ESQUEMA_RESPOSTA},
                },
            )
        except anthropic.APIError as erro:
            raise ErroIA(str(erro)) from erro

        entrada, saida = resposta.usage.input_tokens, resposta.usage.output_tokens
        # Mesmo quando a IA não responde, a chamada custou: tokens e custo são gravados igual
        sem_base = RespostaIA(
            texto=RESPOSTA_SEM_BASE,
            respondida=False,
            trechos_usados=[t.trecho.id for t in trechos],
            tokens_entrada=entrada,
            tokens_saida=saida,
            custo_usd=estimar_custo(self.modelo, entrada, saida),
        )

        if resposta.stop_reason != "end_turn":
            # "refusal" (filtro de segurança) ou "max_tokens" (JSON cortado): encaminha para humano
            log.warning("resposta incompleta da IA", extra={"stop_reason": resposta.stop_reason})
            return sem_base

        texto = next((b.text for b in resposta.content if b.type == "text"), "")
        try:
            dados = json.loads(texto)
            respondida, conteudo = bool(dados["respondida"]), str(dados["resposta"]).strip()
        except (json.JSONDecodeError, KeyError, TypeError):
            log.exception("JSON inválido vindo da IA")
            return sem_base

        if not respondida or not conteudo:
            return sem_base
        return replace(sem_base, texto=conteudo, respondida=True)
