"""Ponto de entrada: `uv run bot`."""

from bot.config import get_settings
from bot.logs import configurar_logs


def main() -> None:
    settings = get_settings()
    configurar_logs(settings.log_nivel)
