"""Logs estruturados em JSON: uma linha por evento, fácil de filtrar e investigar."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CAMPOS_PADRAO = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Campos passados em extra={...} entram no JSON (ex.: request_id, plataforma)
        for chave, valor in vars(record).items():
            if chave not in _CAMPOS_PADRAO:
                evento[chave] = valor
        if record.exc_info:
            evento["erro"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_logs(nivel: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FormatadorJson())
    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel)
    # Bibliotecas barulhentas ficam em WARNING
    for nome in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(nome).setLevel(logging.WARNING)
