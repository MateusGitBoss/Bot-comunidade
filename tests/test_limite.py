from bot.limite import LimitadorUso


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def test_bloqueia_depois_do_maximo_e_libera_quando_a_janela_passa() -> None:
    relogio = Relogio()
    limitador = LimitadorUso(maximo=2, janela_segundos=3600, relogio=relogio)

    assert limitador.tentar("ana")
    relogio.agora += 600
    assert limitador.tentar("ana")
    assert not limitador.tentar("ana")
    # O primeiro uso (t=1000) libera em t=4600; estamos em t=1600
    assert limitador.segundos_para_liberar("ana") == 3000

    relogio.agora = 4600
    assert limitador.tentar("ana")
    assert not limitador.tentar("ana")


def test_cada_usuario_tem_seu_saldo() -> None:
    limitador = LimitadorUso(maximo=1, relogio=Relogio())
    assert limitador.tentar("ana")
    assert not limitador.tentar("ana")
    assert limitador.tentar("bia")


def test_sem_uso_nao_ha_espera() -> None:
    assert LimitadorUso(maximo=1, relogio=Relogio()).segundos_para_liberar("ana") == 0
