import csv
import io
from collections.abc import Sequence

from sac.application.ports_reporting import ReportExportRow

CSV_HEADER: tuple[str, ...] = (
    "numero",
    "marca",
    "status",
    "prioridade",
    "cliente",
    "documento",
    "telefone",
    "email",
    "produtos",
    "defeitos",
    "solucao",
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


def _text(value: str | None) -> str:
    return value if value is not None else ""


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
        row.products,
        row.defects,
        _text(row.solution),
        _text(row.channel),
        _text(row.attendant),
        _text(row.order_code),
        row.opened_at.strftime("%Y-%m-%d %H:%M"),
        row.closed_at.strftime("%Y-%m-%d %H:%M") if row.closed_at is not None else "",
    ]
