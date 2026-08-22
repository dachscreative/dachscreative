"""Exports.

One workbook per run, in exports/, named jobs_YYYY-MM-DD.xlsx. The underscore
matters: run.sh finds the newest export with `ls -1t exports/jobs_*.xlsx`, so a
hyphen here would make "Finished. Newest export:" print nothing.

Two sheets, because they answer different questions:

    Jobs   everything that survived scoring, best first - the sheet you filter
    New    only what appeared since the last run - the sheet you read daily
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import Job

# (header, width, attribute-or-None)
COLUMNS: list[tuple[str, int]] = [
    ("Score", 8),
    ("New", 6),
    ("Title", 46),
    ("Company", 26),
    ("Location", 24),
    ("Remote", 8),
    ("Source", 15),
    ("Posted", 12),
    ("Matched", 40),
    ("Link", 10),
]

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
NEW_FILL = PatternFill("solid", fgColor="E8F2E4")
LINK_FONT = Font(color="0563C1", underline="single")


def _cells(job: Job) -> list[object]:
    return [
        job.score,
        "yes" if job.is_new else "",
        job.title,
        job.company,
        job.location,
        "yes" if job.remote else "",
        job.source,
        job.posted_at.date() if job.posted_at else "",
        ", ".join(job.matched),
        job.url,
    ]


def _fill_sheet(ws: Worksheet, jobs: list[Job], empty_message: str) -> None:
    ws.append([name for name, _ in COLUMNS])

    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")

    for job in jobs:
        ws.append(_cells(job))
        row = ws.max_row

        ws.cell(row=row, column=1).number_format = "0.00"

        # A date written as a date sorts and filters as one. A date written as
        # text sorts alphabetically, which puts 2026-01 after 2025-12 only by
        # luck of the ISO format and breaks the moment the locale changes it.
        if job.posted_at:
            ws.cell(row=row, column=8).number_format = "yyyy-mm-dd"

        # The URL goes in as a hyperlink with short display text, so the column
        # stays narrow and the cell is still clickable.
        link = ws.cell(row=row, column=len(COLUMNS))
        link.value = "open"
        link.hyperlink = job.url
        link.font = LINK_FONT

        if job.is_new:
            for col in range(1, len(COLUMNS) + 1):
                ws.cell(row=row, column=col).fill = NEW_FILL

    for index, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width

    ws.freeze_panes = "A2"
    if jobs:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{ws.max_row}"
    else:
        # An empty run still gets a workbook, so the day is visible rather than
        # missing. Say so in the sheet instead of leaving a bare header row -
        # and say the right thing: an empty New sheet on a run that collected
        # plenty means "nothing new", not "nothing collected".
        ws.append(["", "", empty_message])


def write_workbook(path: Path, kept: list[Job], new: list[Job]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    book = Workbook()
    _fill_sheet(book.active, kept, "Nothing was collected in this run.")
    book.active.title = "Jobs"
    _fill_sheet(
        book.create_sheet("New"),
        new,
        "Nothing new since the last run."
        if kept
        else "Nothing was collected in this run.",
    )

    book.save(path)
    book.close()
    return path


def export_all(exports_dir: Path, kept: list[Job], new: list[Job]) -> list[Path]:
    stamp = date.today().isoformat()
    return [
        write_workbook(exports_dir / f"jobs_{stamp}.xlsx", kept, new),
        write_workbook(exports_dir / "latest.xlsx", kept, new),
    ]
