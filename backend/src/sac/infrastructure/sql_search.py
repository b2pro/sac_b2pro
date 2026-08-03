"""Escape de metacaracteres de LIKE/ILIKE, compartilhado entre repositorios.

repositories_tickets.py e repositories_cadastros.py montam buscas por texto
livre com `.ilike()`/`.like()`; sem escapar `%` e `_` do termo digitado pelo
usuario, esses caracteres viram coringa em vez de literal (ex.: buscar por
"100%" tambem casaria "1000", "100x" etc.).
"""

LIKE_ESCAPE_CHAR = "\\"


def escape_like(term: str) -> str:
    """Escapa `term` para uso com `.ilike(..., escape=LIKE_ESCAPE_CHAR)` /
    `.like(..., escape=LIKE_ESCAPE_CHAR)`, tratando `%` e `_` como literais.

    O backslash e escapado primeiro: escapar `%`/`_` antes duplicaria os
    backslashes que esse primeiro passo introduz.
    """
    escaped = term.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
    escaped = escaped.replace("%", f"{LIKE_ESCAPE_CHAR}%")
    escaped = escaped.replace("_", f"{LIKE_ESCAPE_CHAR}_")
    return escaped
