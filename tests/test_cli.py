from pydantic import SecretStr

from bot.cli import validar
from bot.config import Settings


def test_validar_aponta_o_que_falta() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert validar(settings) == [
        "DISCORD_TOKEN",
        "ANTHROPIC_API_KEY",
        "HASH_SEGREDO (ainda com o valor de exemplo)",
    ]


def test_validar_ok() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        discord_token=SecretStr("d"),
        anthropic_api_key=SecretStr("a"),
        hash_segredo=SecretStr("segredo-de-verdade"),
    )
    assert validar(settings) == []
