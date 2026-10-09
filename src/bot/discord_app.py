"""Camada do Discord: só traduz comandos em chamadas ao ServicoBot e formata a resposta.

Toda regra fica em servico.py; aqui não há lógica de negócio, por isso esta camada é fina.
"""

import logging
from collections.abc import Callable

import discord
from discord import app_commands

from bot.faq import BaseFaq
from bot.servico import TAMANHO_MAXIMO_PERGUNTA, ServicoBot

log = logging.getLogger(__name__)


class ViewFeedback(discord.ui.View):
    """Botões "Ajudou / Não ajudou" embaixo de cada resposta da IA.

    Limitação conhecida: os botões param de funcionar depois de 1 hora ou se o bot reiniciar
    (a View vive em memória). Para feedback tardio seria preciso uma View persistente.
    """

    def __init__(self, servico: ServicoBot, interacao_id: int) -> None:
        super().__init__(timeout=3600)
        self.servico = servico
        self.interacao_id = interacao_id

    async def _registrar(self, interaction: discord.Interaction, util: bool) -> None:
        ok = await self.servico.feedback(self.interacao_id, interaction.user.id, util)
        texto = "Obrigado pelo retorno!" if ok else "Só quem fez a pergunta pode avaliar."
        await interaction.response.send_message(texto, ephemeral=True)

    @discord.ui.button(label="Ajudou", emoji="👍", style=discord.ButtonStyle.success)
    async def ajudou(
        self, interaction: discord.Interaction, _: discord.ui.Button["ViewFeedback"]
    ) -> None:
        await self._registrar(interaction, util=True)

    @discord.ui.button(label="Não ajudou", emoji="👎", style=discord.ButtonStyle.secondary)
    async def nao_ajudou(
        self, interaction: discord.Interaction, _: discord.ui.Button["ViewFeedback"]
    ) -> None:
        await self._registrar(interaction, util=False)


def registrar_comandos(
    tree: app_commands.CommandTree[discord.Client],
    servico: ServicoBot,
    carregar_faq: Callable[[], BaseFaq],
    canal_suporte_id: int | None,
) -> None:
    @tree.command(name="ping", description="Confere se o bot está no ar")
    async def ping(interaction: discord.Interaction) -> None:
        latencia = round(interaction.client.latency * 1000)
        await interaction.response.send_message(f"pong ({latencia} ms)", ephemeral=True)

    @tree.command(name="pergunta", description="Tire uma dúvida sobre acesso, pagamento e curso")
    @app_commands.describe(texto="Sua dúvida, em poucas palavras")
    async def pergunta(
        interaction: discord.Interaction,
        texto: app_commands.Range[str, 3, TAMANHO_MAXIMO_PERGUNTA],
    ) -> None:
        # A IA pode levar alguns segundos e o Discord só espera 3: "defer" mostra "pensando..."
        await interaction.response.defer(thinking=True)
        resultado = await servico.perguntar(interaction.user.id, texto)
        conteudo = f"> {texto}\n{resultado.texto}"
        if resultado.interacao_id is not None and resultado.respondida:
            await interaction.followup.send(
                conteudo, view=ViewFeedback(servico, resultado.interacao_id)
            )
        else:
            await interaction.followup.send(conteudo)

        if resultado.encaminhar_para_humano and canal_suporte_id:
            canal = interaction.client.get_channel(canal_suporte_id)
            if isinstance(canal, discord.TextChannel):
                await canal.send(
                    f"❓ Pergunta sem resposta na base, de {interaction.user.mention}:\n> {texto}"
                )
            else:
                log.warning("canal de suporte não encontrado", extra={"canal": canal_suporte_id})

    @tree.command(name="status-compra", description="Veja se sua compra foi aprovada")
    @app_commands.describe(email="O e-mail usado na compra")
    async def status_compra(interaction: discord.Interaction, email: str) -> None:
        # Efêmera: só quem pediu vê. Status de compra é dado pessoal.
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(await servico.status_compra(email), ephemeral=True)

    @tree.command(name="faq-recarregar", description="Relê os arquivos da FAQ (admins)")
    @app_commands.default_permissions(manage_guild=True)
    async def faq_recarregar(interaction: discord.Interaction) -> None:
        try:
            total = servico.recarregar_faq(carregar_faq())
        except (OSError, ValueError) as erro:
            log.exception("falha ao recarregar a FAQ")
            await interaction.response.send_message(f"Falhou: {erro}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"FAQ recarregada: {total} trechos.", ephemeral=True
        )

    @tree.command(name="uso-hoje", description="Perguntas, feedback e custo de hoje (admins)")
    @app_commands.default_permissions(manage_guild=True)
    async def uso_hoje(interaction: discord.Interaction) -> None:
        r = await servico.resumo_hoje()
        await interaction.response.send_message(
            f"Hoje: {r.perguntas} perguntas, {r.respondidas} respondidas pela base, "
            f"👍 {r.uteis} / 👎 {r.nao_uteis}, custo estimado US$ {r.custo_usd:.4f}",
            ephemeral=True,
        )


class BotComunidade(discord.Client):
    def __init__(self, guild_id: int | None) -> None:
        # Slash commands não precisam ler mensagens: intents mínimas, sem privilégios especiais
        super().__init__(intents=discord.Intents.default())
        self.tree: app_commands.CommandTree[discord.Client] = app_commands.CommandTree(self)
        self.guild_id = guild_id

    async def setup_hook(self) -> None:
        if self.guild_id:
            # Num servidor específico os comandos aparecem na hora (bom para desenvolvimento)
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            sincronizados = await self.tree.sync(guild=guild)
        else:
            sincronizados = await self.tree.sync()
        log.info("comandos sincronizados", extra={"total": len(sincronizados)})

    async def on_ready(self) -> None:
        log.info("bot conectado", extra={"usuario": str(self.user)})
