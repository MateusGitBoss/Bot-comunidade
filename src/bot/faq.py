"""Base de FAQ: quebra os arquivos Markdown em trechos e escolhe os mais relevantes com BM25.

Por que BM25 e não banco vetorial: a FAQ tem dezenas de trechos, não milhões. BM25 roda em
memória, não precisa de serviço extra nem de chamada paga para gerar embeddings, e o resultado
é explicável (dá para ver quais palavras pesaram).
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

# Palavras muito comuns que não ajudam a diferenciar um trecho de outro
STOPWORDS = frozenset(
    [
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "no",
        "na",
        "nos",
        "nas",
        "em",
        "por",
        "para",
        "pra",
        "pro",
        "com",
        "sem",
        "e",
        "ou",
        "mas",
        "que",
        "se",
        "como",
        "qual",
        "quais",
        "quando",
        "onde",
        "quem",
        "eu",
        "voce",
        "voces",
        "ele",
        "ela",
        "eles",
        "elas",
        "meu",
        "minha",
        "meus",
        "minhas",
        "seu",
        "sua",
        "seus",
        "suas",
        "me",
        "te",
        "nos",
        "lhe",
        "isso",
        "isto",
        "esse",
        "essa",
        "este",
        "esta",
        "ja",
        "nao",
        "sim",
        "ao",
        "aos",
        "e",
        "foi",
        "ser",
        "ter",
        "tem",
        "tenho",
        "estou",
        "esta",
        "estao",
        "sao",
        "era",
        "ha",
        "mais",
        "muito",
        "pode",
        "posso",
        "preciso",
    ]
)


@dataclass(frozen=True)
class Trecho:
    arquivo: str
    titulo: str
    texto: str

    @property
    def id(self) -> str:
        return f"{self.arquivo}#{self.titulo}"


@dataclass(frozen=True)
class TrechoEncontrado:
    trecho: Trecho
    pontuacao: float


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento: 'Reembolso' e 'reembólso' viram a mesma palavra."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def tokenizar(texto: str) -> list[str]:
    palavras = re.findall(r"[a-z0-9]+", normalizar(texto))
    return [p for p in palavras if p not in STOPWORDS and len(p) > 1]


def quebrar_markdown(arquivo: str, conteudo: str) -> list[Trecho]:
    """Cada seção `## Título` vira um trecho. O título entra junto porque costuma ser a pergunta."""
    trechos: list[Trecho] = []
    titulo: str | None = None
    linhas: list[str] = []

    def fechar() -> None:
        texto = "\n".join(linhas).strip()
        if titulo and texto:
            trechos.append(Trecho(arquivo=arquivo, titulo=titulo, texto=texto))

    for linha in conteudo.splitlines():
        if linha.startswith("## "):
            fechar()
            titulo, linhas = linha[3:].strip(), []
        elif titulo is not None:
            linhas.append(linha)
    fechar()
    return trechos


class BaseFaq:
    def __init__(self, trechos: list[Trecho]) -> None:
        if not trechos:
            raise ValueError("A FAQ está vazia: nenhum trecho com título '## ' encontrado")
        self.trechos = trechos
        self._indice = BM25Okapi([tokenizar(f"{t.titulo} {t.texto}") for t in trechos])

    @classmethod
    def carregar(cls, diretorio: Path) -> "BaseFaq":
        trechos: list[Trecho] = []
        for caminho in sorted(diretorio.glob("*.md")):
            trechos.extend(quebrar_markdown(caminho.name, caminho.read_text(encoding="utf-8")))
        return cls(trechos)

    def buscar(
        self, pergunta: str, limite: int = 3, pontuacao_minima: float = 1.0
    ) -> list[TrechoEncontrado]:
        """Devolve os trechos mais relevantes. Lista vazia significa 'a base não cobre isso'.

        A pontuação mínima evita mandar para a IA trechos que só batem por acaso em uma
        palavra genérica; sem trecho relevante nem chamamos a API (economia e menos risco
        de resposta inventada).
        """
        termos = tokenizar(pergunta)
        if not termos:
            return []
        pontuacoes = self._indice.get_scores(termos)
        ordenados = sorted(zip(self.trechos, pontuacoes, strict=True), key=lambda par: -par[1])
        return [
            TrechoEncontrado(trecho=t, pontuacao=float(p))
            for t, p in ordenados[:limite]
            if p >= pontuacao_minima
        ]
