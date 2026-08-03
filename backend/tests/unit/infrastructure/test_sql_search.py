from sac.infrastructure.sql_search import escape_like


def test_escapa_percent_e_underscore() -> None:
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"


def test_escapa_backslash_antes_dos_demais_para_nao_dobrar() -> None:
    assert escape_like("a\\b") == "a\\\\b"
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"


def test_termo_sem_metacaracteres_fica_inalterado() -> None:
    assert escape_like("mariana") == "mariana"
