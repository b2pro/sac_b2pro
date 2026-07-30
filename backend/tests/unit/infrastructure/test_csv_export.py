from datetime import UTC, datetime

from sac.application.ports_reporting import ReportExportRow
from sac.infrastructure.csv_export import CSV_HEADER, csv_line, export_row_values


def _row() -> ReportExportRow:
    return ReportExportRow(
        number=7,
        brand="KODI",
        status="finalizado",
        priority="media",
        customer_name='Cliente "Especial"',
        customer_document="52998224725",
        customer_phone=None,
        customer_email=None,
        products="Alicate x2",
        defects="Oxidacao x2",
        solution="Troca, pelo mesmo item",
        channel=None,
        attendant="Ana",
        order_code=None,
        opened_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        closed_at=None,
    )


def test_csv_line_escapa_aspas_e_virgulas() -> None:
    line = csv_line(export_row_values(_row()))
    assert '"Cliente ""Especial"""' in line
    assert '"Troca, pelo mesmo item"' in line
    assert line.endswith("\r\n")
    assert line.startswith("7,KODI,finalizado")


def test_header_e_valores_tem_mesmo_tamanho() -> None:
    assert len(CSV_HEADER) == len(export_row_values(_row()))
