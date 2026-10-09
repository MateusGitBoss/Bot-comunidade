"""Ponto de entrada: `uv run bot` liga o bot (aplica as migrações antes)."""

import asyncio
import logging
import sys

import anthropic

from bot.config import Settings, get_settings
from bot.discord_app import BotComunidade, registrar_comandos
from bot.faq import BaseFaq
from bot.ia import AssistenteFaq
from bot.limite import LimitadorUso
from bot.logs import configurar_logs
from bot.repositorio import RepositorioPostgres
from bot.servico import ServicoBot
from bot.vendas import ClienteVendas

log = logging.getLogger(__name__)


def validar(settings: Settings) -> list[str]:
    """Falha cedo, com mensagem clara, em vez de quebrar na primeira pergunta."""
    faltando = []
    if not settings.discord_token.get_secret_value():
        faltando.append("DISCORD_TOKEN")
    if not settings.anthropic_api_key.get_secret_value():
        faltando.append("ANTHROPIC_API_KEY")
    if settings.hash_segredo.get_secret_value() == "troque-este-segredo":
        faltando.append("HASH_SEGREDO (ainda com o valor de exemplo)")
    return faltando


async def rodar(settings: Settings) -> None:
    repositorio = await RepositorioPostgres.abrir(settings.database_url)
    vendas = ClienteVendas.criar(
        settings.vendas_api_url, settings.vendas_api_token.get_secret_value()
    )
    try:
        novas = await repositorio.migrar()
        if novas:
            log.info("migrações aplicadas", extra={"versoes": novas})

        def carregar_faq() -> BaseFaq:
            return BaseFaq.carregar(settings.faq_dir)

        faq = carregar_faq()
        cliente_ia = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=30, max_retries=2
        )
        assistente = AssistenteFaq.com_prompt_de_arquivo(
            cliente_ia, settings.prompt_path, settings.modelo, settings.max_tokens_resposta
        )
        servico = ServicoBot(
            faq=faq,
            assistente=assistente,
            repositorio=repositorio,
            limitador=LimitadorUso(settings.limite_perguntas_hora),
            vendas=vendas,
            segredo_hash=settings.hash_segredo.get_secret_value(),
            trechos_por_pergunta=settings.trechos_por_pergunta,
        )
        bot = BotComunidade(settings.discord_guild_id)
        registrar_comandos(bot.tree, servico, carregar_faq, settings.canal_suporte_id)
        log.info(
            "iniciando bot", extra={"trechos_faq": len(faq.trechos), "modelo": settings.modelo}
        )
        async with bot:
            await bot.start(settings.discord_token.get_secret_value())
    finally:
        await vendas.fechar()
        await repositorio.fechar()


def main() -> None:
    settings = get_settings()
    configurar_logs(settings.log_nivel)
    faltando = validar(settings)
    if faltando:
        log.error("configuração incompleta", extra={"faltando": faltando})
        sys.exit(1)
    asyncio.run(rodar(settings))
