"""
Generate invoice PDFs from an HTML template.

Behavior:
- Loads invoice data from a .env file.
- Lists month/year pairs that already have generated invoices (supports old and new filename formats).
- Prompts for the month/year to generate.
- Renders invoice_template.html via Jinja2.
- Generates a PDF using Playwright (Chromium).
- Stores PDFs in ./invoices and tracks invoice numbers in invoice_number.txt.
- Generates filenames as: Invoice_YYYY_MM_#N.pdf (sortable by name).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright


REQUIRED_ENV_KEYS: Tuple[str, ...] = (
    "COMPANY_NAME",
    "COMPANY_ID",
    "BILL_FROM",
    "BILL_TO",
    "SERVICE_TITLE",
    "SERVICE_DESC",
    "CURRENCY",
    "AMOUNT",
    "BENEFICIARY_NAME",
    "IBAN",
    "SWIFT",
    "BANK_NAME",
    "BANK_ADDRESS",
    "INTERMEDIARY_BANK_NAME",
    "INTERMEDIARY_BANK_SWIFT",
    "SUPPORT_EMAIL",
)


@dataclass(frozen=True)
class InvoiceTarget:
    month: int
    year: int

    @property
    def month_str(self) -> str:
        return f"{self.month:02d}"

    @property
    def year_str(self) -> str:
        return f"{self.year:04d}"

    @property
    def ym_str(self) -> str:
        return f"{self.year_str}-{self.month_str}"


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _normalize_env_value(value: str) -> str:
    return value.replace("\\n", "\n")


def _load_env(env_path: Path) -> Dict[str, str]:
    values = dotenv_values(env_path)
    env: Dict[str, str] = {}
    for k, v in values.items():
        if k is None or v is None:
            continue
        env[str(k)] = _normalize_env_value(str(v))

    missing = [k for k in REQUIRED_ENV_KEYS if k not in env or env[k] == ""]
    if missing:
        raise ValueError(f"Missing required keys in .env: {', '.join(missing)}")

    return env


def _read_last_invoice_number(path: Path) -> int:
    if not path.exists():
        return 0
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid invoice_number.txt content: {raw!r}") from exc


def _write_last_invoice_number(path: Path, value: int) -> None:
    path.write_text(f"{value}\n", encoding="utf-8")


def _parse_invoice_filename(
    name: str,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    pattern_new = re.compile(r"^Invoice_(\d{4})_(\d{2})_#(\d+)\.pdf$")
    pattern_old = re.compile(r"^Invoice_(\d{2})_(\d{4})_#(\d+)\.pdf$")

    m_new = pattern_new.match(name)
    if m_new:
        year = int(m_new.group(1))
        month = int(m_new.group(2))
        number = int(m_new.group(3))
        return year, month, number

    m_old = pattern_old.match(name)
    if m_old:
        month = int(m_old.group(1))
        year = int(m_old.group(2))
        number = int(m_old.group(3))
        return year, month, number

    return None, None, None


def _list_generated_targets(invoices_dir: Path) -> List[InvoiceTarget]:
    targets: set[Tuple[int, int]] = set()
    if not invoices_dir.exists():
        return []

    for p in invoices_dir.glob("Invoice_*.pdf"):
        year, month, _ = _parse_invoice_filename(p.name)
        if year is None or month is None:
            continue
        if 1 <= month <= 12:
            targets.add((year, month))

    return [InvoiceTarget(month=m, year=y) for (y, m) in sorted(targets)]


def _max_invoice_number_from_pdfs(invoices_dir: Path) -> int:
    max_n = 0
    if not invoices_dir.exists():
        return 0

    for p in invoices_dir.glob("Invoice_*.pdf"):
        _, _, number = _parse_invoice_filename(p.name)
        if number is None:
            continue
        if number > max_n:
            max_n = number
    return max_n


def _format_targets(targets: Sequence[InvoiceTarget]) -> str:
    if not targets:
        return "none yet"
    return ", ".join(t.ym_str for t in targets)


def _prompt_target(default_year: int) -> InvoiceTarget:
    raw = input("Which month to generate? (e.g. 2, 02, 02/2026, 2026-02): ").strip()
    if not raw:
        raise ValueError("No input provided.")

    m1 = re.fullmatch(r"(\d{1,2})", raw)
    m2 = re.fullmatch(r"(\d{1,2})/(\d{4})", raw)
    m3 = re.fullmatch(r"(\d{4})-(\d{1,2})", raw)

    if m1:
        month = int(m1.group(1))
        year = default_year
    elif m2:
        month = int(m2.group(1))
        year = int(m2.group(2))
    elif m3:
        year = int(m3.group(1))
        month = int(m3.group(2))
    else:
        raise ValueError("Invalid format. Use: M, MM, MM/YYYY, or YYYY-MM.")

    if not (1 <= month <= 12):
        raise ValueError("Month must be between 1 and 12.")
    if not (1900 <= year <= 3000):
        raise ValueError("Year looks invalid.")

    return InvoiceTarget(month=month, year=year)


def _ensure_playwright_ready() -> None:
    if shutil.which("node") is None:
        raise RuntimeError("node not found in PATH. Install Node.js to use Playwright.")
    if shutil.which("python") is None and shutil.which("python3") is None:
        raise RuntimeError("python not found in PATH.")


def _render_html(
    template_dir: Path, template_name: str, context: Dict[str, str]
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)
    return template.render(**context)


def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
        )
        browser.close()


def main() -> int:
    base = _base_dir()
    env_path = base / ".env"
    template_path = base / "invoice_template.html"
    invoices_dir = base / "invoices"
    invoice_number_path = base / "invoice_number.txt"

    if not env_path.exists():
        print(f"Error: .env file not found: {env_path}")
        return 1

    if not template_path.exists():
        print(f"Error: HTML template not found: {template_path}")
        return 1

    invoices_dir.mkdir(parents=True, exist_ok=True)

    generated = _list_generated_targets(invoices_dir)
    print(
        f"Already generated months (detected from filenames): {_format_targets(generated)}"
    )

    today = date.today()
    try:
        target = _prompt_target(default_year=today.year)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    if any(t.year == target.year and t.month == target.month for t in generated):
        print(f"Warning: an invoice for {target.ym_str} already exists in ./invoices")

    try:
        _ensure_playwright_ready()
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    try:
        env = _load_env(env_path)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    last_from_file = _read_last_invoice_number(invoice_number_path)
    last_from_pdfs = _max_invoice_number_from_pdfs(invoices_dir)
    last_number = max(last_from_file, last_from_pdfs)
    next_number = last_number + 1

    creation_date = f"{target.year_str}-{target.month_str}-01"
    due_date = f"{target.year_str}-{target.month_str}-30"

    context: Dict[str, str] = dict(env)
    context.update(
        {
            "INVOICE_NUMBER": str(next_number),
            "CREATION_DATE": creation_date,
            "DUE_DATE": due_date,
        }
    )

    pdf_name = f"Invoice_{target.year_str}_{target.month_str}_#{next_number}.pdf"
    pdf_out_path = invoices_dir / pdf_name
    if pdf_out_path.exists():
        print(f"Error: output PDF already exists: {pdf_out_path.name}")
        return 1

    temp_html = base / "invoice_temp.html"
    temp_pdf = base / "invoice_temp.pdf"

    try:
        html = _render_html(
            template_dir=base, template_name=template_path.name, context=context
        )
        temp_html.write_text(html, encoding="utf-8")

        _html_to_pdf(temp_html, temp_pdf)
        if not temp_pdf.exists():
            print("Error: PDF was not generated.")
            return 1

        shutil.move(str(temp_pdf), str(pdf_out_path))
        _write_last_invoice_number(invoice_number_path, next_number)

        print(f"PDF generated: {pdf_out_path}")
        return 0
    finally:
        for p in (temp_html, temp_pdf):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
