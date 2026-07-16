"""
xlsm_reader.py — dependency-free reader for .xlsx/.xlsm workbooks.

Uses only the Python standard library (zipfile + xml.etree), so no
openpyxl/pandas install is required on the machine running the testing suite.

Reads CACHED cell values (including formula results as last saved by Excel).

Usage:
    from xlsm_reader import load_sheet, sheet_names

    names = sheet_names(path)
    rows = load_sheet(path, "ValidationScenarios")   # list of list of values
"""

import re
import zipfile
import xml.etree.ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _q(tag):
    return f"{{{NS_MAIN}}}{tag}"


def _col_to_index(cell_ref):
    """'BC12' -> zero-based column index (54)."""
    m = re.match(r"([A-Z]+)", cell_ref)
    if not m:
        return 0
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1


def _load_shared_strings(zf):
    strings = []
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return strings
    root = ET.fromstring(data)
    for si in root.findall(_q("si")):
        # A shared string may be split across multiple <r><t> runs
        text = "".join(t.text or "" for t in si.iter(_q("t")))
        strings.append(text)
    return strings


def _sheet_name_to_path(zf):
    """Map sheet name -> zip path (e.g. 'xl/worksheets/sheet3.xml')."""
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

    rid_to_target = {}
    for rel in rels_root.findall(f"{{{NS_PKG_REL}}}Relationship"):
        target = rel.get("Target")
        if target.startswith("/"):
            target = target.lstrip("/")
        else:
            target = "xl/" + target
        rid_to_target[rel.get("Id")] = target

    mapping = {}
    sheets_el = wb_root.find(_q("sheets"))
    if sheets_el is None:
        return mapping
    for sheet in sheets_el.findall(_q("sheet")):
        name = sheet.get("name")
        rid = sheet.get(f"{{{NS_REL_DOC}}}id")
        target = rid_to_target.get(rid)
        if target:
            mapping[name] = target
    return mapping


def sheet_names(path):
    """Return the list of sheet names in the workbook."""
    with zipfile.ZipFile(path) as zf:
        return list(_sheet_name_to_path(zf).keys())


def _cell_value(cell, shared_strings):
    ctype = cell.get("t", "n")
    v_el = cell.find(_q("v"))

    if ctype == "inlineStr":
        is_el = cell.find(_q("is"))
        if is_el is not None:
            return "".join(t.text or "" for t in is_el.iter(_q("t")))
        return None

    if v_el is None or v_el.text is None:
        return None
    raw = v_el.text

    if ctype == "s":  # shared string
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if ctype == "b":  # boolean
        return raw in ("1", "true", "TRUE")
    if ctype in ("str", "e"):  # formula string result / error
        return raw
    # numeric
    try:
        f = float(raw)
        return int(f) if f == int(f) else f
    except ValueError:
        return raw


def load_sheet(path, sheet_name):
    """
    Load one sheet as a list of rows; each row is a list of cell values.
    Empty cells are None. Rows are padded so all rows share the max width.
    Trailing all-empty rows are dropped.
    """
    with zipfile.ZipFile(path) as zf:
        mapping = _sheet_name_to_path(zf)
        if sheet_name not in mapping:
            raise KeyError(
                f"Sheet '{sheet_name}' not found. Available: {list(mapping.keys())}"
            )
        shared_strings = _load_shared_strings(zf)
        root = ET.fromstring(zf.read(mapping[sheet_name]))

    rows = {}
    max_col = 0
    sheet_data = root.find(_q("sheetData"))
    if sheet_data is None:
        return []

    for row_el in sheet_data.findall(_q("row")):
        r_idx = int(row_el.get("r", len(rows) + 1)) - 1
        row_vals = {}
        for cell in row_el.findall(_q("c")):
            ref = cell.get("r", "")
            c_idx = _col_to_index(ref)
            val = _cell_value(cell, shared_strings)
            if val is not None and val != "":
                row_vals[c_idx] = val
                max_col = max(max_col, c_idx)
        rows[r_idx] = row_vals

    if not rows:
        return []

    max_row = max(rows.keys())
    result = []
    for r in range(max_row + 1):
        row_vals = rows.get(r, {})
        result.append([row_vals.get(c) for c in range(max_col + 1)])

    # Drop trailing empty rows
    while result and all(v is None for v in result[-1]):
        result.pop()
    return result


def load_all_sheets(path):
    """Load every sheet -> {sheet_name: rows}."""
    return {name: load_sheet(path, name) for name in sheet_names(path)}


def defined_names(path):
    """Return workbook defined names -> {name: reference_text}."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    names = {}
    dn_container = root.find(_q("definedNames"))
    if dn_container is None:
        return names
    for dn in dn_container.findall(_q("definedName")):
        name = dn.get("name")
        if name and dn.text:
            names[name] = dn.text
    return names


def load_sheet_formulas(path, sheet_name):
    """
    Load one sheet as {(row_idx, col_idx): formula_string} for every cell
    that contains a formula (zero-based indices).
    """
    with zipfile.ZipFile(path) as zf:
        mapping = _sheet_name_to_path(zf)
        if sheet_name not in mapping:
            raise KeyError(
                f"Sheet '{sheet_name}' not found. Available: {list(mapping.keys())}"
            )
        root = ET.fromstring(zf.read(mapping[sheet_name]))

    formulas = {}
    sheet_data = root.find(_q("sheetData"))
    if sheet_data is None:
        return formulas
    for row_el in sheet_data.findall(_q("row")):
        r_idx = int(row_el.get("r", 0)) - 1
        for cell in row_el.findall(_q("c")):
            f_el = cell.find(_q("f"))
            if f_el is not None and f_el.text:
                c_idx = _col_to_index(cell.get("r", ""))
                formulas[(r_idx, c_idx)] = f_el.text
    return formulas
