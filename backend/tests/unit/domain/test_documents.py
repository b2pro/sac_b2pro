import pytest

from sac.domain.documents import (
    is_valid_cnpj,
    is_valid_cpf,
    normalize_digits,
    validate_document,
    validate_state,
)
from sac.domain.errors import ValidationError


def test_normalize_digits() -> None:
    assert normalize_digits("529.982.247-25") == "52998224725"
    assert normalize_digits("(54) 99982-3566") == "54999823566"
    assert normalize_digits("abc") == ""


def test_cpf_valido() -> None:
    assert is_valid_cpf("52998224725")


@pytest.mark.parametrize("digits", ["52998224724", "11111111111", "5299822472", ""])
def test_cpf_invalido(digits: str) -> None:
    assert not is_valid_cpf(digits)


def test_cnpj_valido() -> None:
    assert is_valid_cnpj("11222333000181")


@pytest.mark.parametrize("digits", ["11222333000180", "11111111111111", "1122233300018"])
def test_cnpj_invalido(digits: str) -> None:
    assert not is_valid_cnpj(digits)


def test_validate_document_normaliza_e_aceita() -> None:
    assert validate_document("529.982.247-25") == "52998224725"
    assert validate_document("11.222.333/0001-81") == "11222333000181"


@pytest.mark.parametrize("value", ["123", "529.982.247-24", "11.222.333/0001-80", ""])
def test_validate_document_rejeita(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_document(value)


def test_validate_state() -> None:
    assert validate_state(" rs ") == "RS"
    with pytest.raises(ValidationError):
        validate_state("XX")
