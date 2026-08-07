import re

from sac.domain.errors import ValidationError

_NON_DIGITS = re.compile(r"\D")

BR_STATES = frozenset(
    {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }
)


def normalize_digits(value: str) -> str:
    return _NON_DIGITS.sub("", value)


def _cpf_digit(digits: str, start_weight: int) -> int:
    total = sum(int(d) * w for d, w in zip(digits, range(start_weight, 1, -1), strict=True))
    remainder = (total * 10) % 11
    return 0 if remainder == 10 else remainder


def is_valid_cpf(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    return int(digits[9]) == _cpf_digit(digits[:9], 10) and int(digits[10]) == _cpf_digit(
        digits[:10], 11
    )


def _cnpj_digit(digits: str, weights: list[int]) -> int:
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    first = _cnpj_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _cnpj_digit(digits[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return int(digits[12]) == first and int(digits[13]) == second


def validate_document(value: str) -> str:
    digits = normalize_digits(value)
    if len(digits) == 11 and is_valid_cpf(digits):
        return digits
    if len(digits) == 14 and is_valid_cnpj(digits):
        return digits
    raise ValidationError(
        "documento inválido: informe um CPF ou CNPJ válido", details={"document": value}
    )


def validate_state(value: str) -> str:
    state = value.strip().upper()
    if state not in BR_STATES:
        raise ValidationError(f"UF inválida: {value}")
    return state
