from pathlib import Path

import pytest

from bot.faq import BaseFaq, quebrar_markdown, tokenizar

FAQ_DIR = Path(__file__).parent.parent / "docs" / "faq"


@pytest.fixture(scope="module")
def faq() -> BaseFaq:
    return BaseFaq.carregar(FAQ_DIR)


def test_tokenizar_remove_acento_maiuscula_e_stopwords() -> None:
    assert tokenizar("Como peço o REEMBOLSO do cartão?") == ["peco", "reembolso", "cartao"]


def test_quebrar_markdown_um_trecho_por_secao() -> None:
    conteudo = "# Título\nintro ignorada\n## Pergunta 1\nResposta 1\n\n## Pergunta 2\nResposta 2\n"
    trechos = quebrar_markdown("x.md", conteudo)
    assert [t.titulo for t in trechos] == ["Pergunta 1", "Pergunta 2"]
    assert trechos[0].texto == "Resposta 1"
    assert trechos[1].id == "x.md#Pergunta 2"


def test_secao_sem_texto_e_ignorada() -> None:
    assert quebrar_markdown("x.md", "## Vazia\n\n## Cheia\ntexto") == [
        quebrar_markdown("x.md", "## Cheia\ntexto")[0]
    ]


def test_faq_de_exemplo_carrega_todos_os_arquivos(faq: BaseFaq) -> None:
    arquivos = {t.arquivo for t in faq.trechos}
    assert arquivos == {"acesso.md", "comunidade.md", "pagamento.md", "reembolso.md"}
    assert len(faq.trechos) >= 20


@pytest.mark.parametrize(
    ("pergunta", "titulo_esperado"),
    [
        ("quero meu dinheiro de volta, como faço o reembolso?", "Como peço o reembolso?"),
        ("paguei boleto e nao liberou", "Comprei no boleto e ainda não tenho acesso"),
        ("o certificado sai quando?", "Como funciona o certificado?"),
        ("dá pra parcelar no cartão?", "Posso parcelar?"),
        ("tem live?", "Tem aula ao vivo?"),
    ],
)
def test_busca_traz_o_trecho_certo_entre_os_enviados_para_a_ia(
    faq: BaseFaq, pergunta: str, titulo_esperado: str
) -> None:
    # Os 3 trechos vão juntos para a IA, então basta o certo estar entre eles
    titulos = [r.trecho.titulo for r in faq.buscar(pergunta, limite=3)]
    assert titulo_esperado in titulos


def test_pergunta_fora_do_assunto_nao_traz_trecho(faq: BaseFaq) -> None:
    assert faq.buscar("qual a capital da Mongólia?") == []


def test_pergunta_so_com_stopwords_nao_traz_trecho(faq: BaseFaq) -> None:
    assert faq.buscar("e o que é isso?") == []


def test_respeita_o_limite(faq: BaseFaq) -> None:
    assert len(faq.buscar("acesso curso compra pagamento", limite=2)) <= 2


def test_faq_vazia_falha_cedo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="vazia"):
        BaseFaq.carregar(tmp_path)
