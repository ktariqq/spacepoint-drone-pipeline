"""
SpacePoint - HTML -> PDF conversion for the Mission Report
Author: Kommal

Converts the existing self-contained HTML report (produced unchanged by
generate_report.generate_report()) into a PDF, using xhtml2pdf - a pure
Python library (no system binary like wkhtmltopdf/Chromium needed, which
matters on Streamlit Community Cloud where you can't install extra
system packages). This does NOT touch report_template.html or the
report's own Jinja2 templating logic at all - it takes the
already-rendered HTML string as input and converts it, so only the
final export format changes (.html -> .pdf), nothing about the report's
content or layout logic.
"""

from io import BytesIO

from xhtml2pdf import pisa


def html_to_pdf_bytes(html_content: str) -> tuple[bytes | None, str | None]:
    """Returns (pdf_bytes, error_message). error_message is None on success."""
    buffer = BytesIO()
    try:
        result = pisa.CreatePDF(src=html_content, dest=buffer)
    except Exception as exc:
        return None, f"PDF conversion raised an exception: {exc}"

    if result.err:
        return None, (
            f"PDF conversion reported {result.err} error(s). This usually means the "
            "report's HTML/CSS uses something xhtml2pdf doesn't support (e.g. flexbox/grid). "
            "Simplify report_template.html's CSS if this keeps happening."
        )

    return buffer.getvalue(), None