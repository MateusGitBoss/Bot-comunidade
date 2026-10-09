"""Configuração lida de variáveis de ambiente (ou de um arquivo .env em desenvolvimento)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: SecretStr = SecretStr("")
    # Servidor de testes: comandos aparecem na hora. Sem ele, o Discord leva até 1h para propagar.
    discord_guild_id: int | None = None
    # Canal onde caem as perguntas que o bot não soube responder
    canal_suporte_id: int | None = None

    anthropic_api_key: SecretStr = SecretStr("")
    # Haiku: modelo mais barato e rápido, suficiente para responder com base em trechos prontos
    modelo: str = "claude-haiku-5-5"
    max_tokens_resposta: int = 1024

    faq_dir: Path = Path("docs/faq")
    prompt_path: Path = Path("prompts/sistema.md")
    trechos_por_pergunta: int = 3

    database_url: str = "postgresql://postgres:postgres@localhost:5432/bot"
    # Segredo do HMAC que transforma o ID do Discord em hash antes de gravar (LGPD)
    hash_segredo: SecretStr = SecretStr("troque-este-segredo")

    limite_perguntas_hora: int = Field(default=10, ge=1)

    # API do projeto webhook-vendas (P2)
    vendas_api_url: str = "http://localhost:8000"
    vendas_api_token: SecretStr = SecretStr("")

    log_nivel: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
