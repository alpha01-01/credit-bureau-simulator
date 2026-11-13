"""Write rendered rows to CSV or XLSX bytes, deterministically.

The same world, provider and month always give byte-identical files, so a
file's SHA-256 can be compared across runs.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime

from openpyxl import Workbook

from .render import RenderedFile

EXTENSIONS = {"CSV": "csv", "XLSX": "xlsx"}


def to_bytes(rendered: RenderedFile, file_format: str, period: date) -> bytes:
    if file_format == "CSV":
        return _csv(rendered)
    if file_format == "XLSX":
        return _xlsx(rendered, period)
    raise ValueError(f"Unknown file format {file_format!r}")


def _csv(rendered: RenderedFile) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(rendered.layout.names)
    writer.writerows(rendered.rows)
    return buffer.getvalue().encode("utf-8")


def _xlsx(rendered: RenderedFile, period: date) -> bytes:
    stamp = datetime(period.year, period.month, period.day)
    workbook = Workbook(write_only=True)
    workbook.properties.creator = "provider extract"
    workbook.properties.created = stamp
    workbook.properties.modified = stamp
    sheet = workbook.create_sheet("Data")
    sheet.append(list(rendered.layout.names))
    phones = set(rendered.phone_columns)
    for row in rendered.rows:
        # Text everywhere, as exported; phone numbers that have become plain
        # digits (leading zero already lost) are stored as numbers, as Excel does.
        sheet.append(
            [
                int(value)
                if i in phones and value.isdigit() and not value.startswith("0")
                else value
                for i, value in enumerate(row)
            ]
        )
    raw = io.BytesIO()
    workbook.save(raw)
    return _normalise_zip(raw.getvalue(), (period.year, period.month, period.day, 0, 0, 0))


_DOC_TIMESTAMP = re.compile(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:)")


def _normalise_zip(data: bytes, date_time: tuple[int, int, int, int, int, int]) -> bytes:
    """Rewrite an XLSX archive so its bytes are reproducible.

    openpyxl stamps the save time into docProps/core.xml and every zip entry;
    both are replaced with the reporting date.
    """
    stamp = datetime(*date_time).strftime("%Y-%m-%dT%H:%M:%SZ").encode("ascii")
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                content = _DOC_TIMESTAMP.sub(rb"\g<1>" + stamp + rb"\g<2>", content)
            entry = zipfile.ZipInfo(info.filename, date_time=date_time)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            target.writestr(entry, content)
    return out.getvalue()
