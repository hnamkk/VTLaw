from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "corpus" / "kb-v2" / "corpus-checklist.xlsx"


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _inline_cell(ref: str, value: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(value)}</t></is></c>'


def _row(index: int, values: list[str]) -> str:
    cells: list[str] = []
    for offset, value in enumerate(values, start=1):
        column = _column_name(offset)
        cells.append(_inline_cell(f"{column}{index}", value))
    return f'<row r="{index}">{"".join(cells)}</row>'


def _column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_workbook() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "priority",
        "document_title",
        "document_number",
        "local_file",
        "source_url",
        "downloaded_at",
        "role",
        "depends_on",
        "notes",
    ]
    sample_row = [
        "1",
        "Luat Trat tu an toan giao thong duong bo",
        "36/2024/QH15",
        "raw-docx/batch-01/01_luat_ttatgt_2024.docx",
        "https://example.gov.vn/luat-36-2024-qh15.docx",
        "2026-07-03",
        "base",
        "",
        "Luat nen GTVT duong bo",
    ]

    sheet1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>
    <col min="1" max="1" width="12" customWidth="1"/>
    <col min="2" max="2" width="36" customWidth="1"/>
    <col min="3" max="3" width="22" customWidth="1"/>
    <col min="4" max="4" width="42" customWidth="1"/>
    <col min="5" max="5" width="42" customWidth="1"/>
    <col min="6" max="6" width="14" customWidth="1"/>
    <col min="7" max="7" width="18" customWidth="1"/>
    <col min="8" max="8" width="22" customWidth="1"/>
    <col min="9" max="9" width="34" customWidth="1"/>
  </cols>
  <sheetData>
{rows}
  </sheetData>
  <dataValidations count="2">
    <dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="A2:A500">
      <formula1>=PriorityOptions</formula1>
    </dataValidation>
    <dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" sqref="G2:G500">
      <formula1>=RoleOptions</formula1>
    </dataValidation>
  </dataValidations>
  <autoFilter ref="A1:I500"/>
</worksheet>
"""
    sheet2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
{rows}
  </sheetData>
</worksheet>
"""

    sheet1_rows = "\n".join(
        [
            f"    {_row(1, headers)}",
            f"    {_row(2, sample_row)}",
        ]
    )
    sheet2_rows = "\n".join(
        [
            f"    {_row(1, ['priority', 'role'])}",
            f"    {_row(2, ['1', 'base'])}",
            f"    {_row(3, ['2', 'amendment'])}",
            f"    {_row(4, ['3', 'replacement'])}",
            f"    {_row(5, ['', 'guidance'])}",
            f"    {_row(6, ['', 'foundation'])}",
            f"    {_row(7, ['', 'technical'])}",
            f"    {_row(8, ['', 'reference'])}",
        ]
    )

    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews><workbookView/></bookViews>
  <sheets>
    <sheet name="CorpusChecklist" sheetId="1" r:id="rId1"/>
    <sheet name="Lists" sheetId="2" state="hidden" r:id="rId2"/>
  </sheets>
  <definedNames>
    <definedName name="PriorityOptions">Lists!$A$2:$A$4</definedName>
    <definedName name="RoleOptions">Lists!$B$2:$B$8</definedName>
  </definedNames>
</workbook>
""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
""",
        "xl/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
""",
        "xl/worksheets/sheet1.xml": sheet1.format(rows=sheet1_rows),
        "xl/worksheets/sheet2.xml": sheet2.format(rows=sheet2_rows),
    }

    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))


if __name__ == "__main__":
    build_workbook()
