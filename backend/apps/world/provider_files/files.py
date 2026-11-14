"""Write rendered rows as the standard's file format: CSV with a pipe delimiter.

The same world, provider and month always give byte-identical files, so a
file's SHA-256 can be compared across runs.
"""

from __future__ import annotations

import csv
import io

from apps.standards.submission_template import DELIMITER

from .render import RenderedFile


def to_bytes(rendered: RenderedFile) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=DELIMITER, lineterminator="\r\n")
    writer.writerow(rendered.layout.names)
    writer.writerows(rendered.rows)
    return buffer.getvalue().encode("utf-8")
