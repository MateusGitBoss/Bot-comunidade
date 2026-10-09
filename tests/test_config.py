from bot.config import Settings


def test_modelo_padrao_e_barato() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.modelo == "claude-haiku-5-5"
    assert settings.limite_perguntas_hora == 10


def test_le_variaveis_de_ambiente(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("LIMITE_PERGUNTAS_HORA", "3")
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.limite_perguntas_hora == 3
    assert settings.discord_token.get_secret_value() == "abc"
