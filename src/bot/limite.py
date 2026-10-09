"""Limite de perguntas por usuário por hora: protege o custo da API contra abuso ou spam."""

import time
from collections import defaultdict, deque
from collections.abc import Callable


class LimitadorUso:
    """Janela deslizante em memória.

    Limitação conhecida: o contador zera quando o bot reinicia e não é compartilhado entre
    duas instâncias. Para um bot com uma instância só, é suficiente; com várias, o lugar
    certo seria o Postgres ou um Redis.
    """

    def __init__(
        self,
        maximo: int,
        janela_segundos: float = 3600,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.maximo = maximo
        self.janela = janela_segundos
        self._relogio = relogio
        self._usos: dict[str, deque[float]] = defaultdict(deque)

    def _limpar(self, usuario: str, agora: float) -> deque[float]:
        usos = self._usos[usuario]
        while usos and agora - usos[0] >= self.janela:
            usos.popleft()
        return usos

    def tentar(self, usuario: str) -> bool:
        """Registra um uso se ainda houver saldo. Devolve False quando estourou o limite."""
        agora = self._relogio()
        usos = self._limpar(usuario, agora)
        if len(usos) >= self.maximo:
            return False
        usos.append(agora)
        return True

    def segundos_para_liberar(self, usuario: str) -> int:
        agora = self._relogio()
        usos = self._limpar(usuario, agora)
        if len(usos) < self.maximo:
            return 0
        return max(1, int(self.janela - (agora - usos[0])))
