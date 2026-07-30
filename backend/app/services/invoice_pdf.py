"""Convert invoice HTML to PDF bytes."""
from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def html_to_pdf_bytes(html: str) -> bytes:
    """Render HTML string to a single PDF document."""
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise RuntimeError(
            "PDF export requires xhtml2pdf. Install with: pip install xhtml2pdf"
        ) from exc

    output = BytesIO()
    result = pisa.CreatePDF(src=html, dest=output, encoding="utf-8")
    if result.err:
        logger.error("xhtml2pdf errors while rendering invoice PDF")
        raise RuntimeError("Failed to generate PDF from invoice HTML")
    return output.getvalue()


def invoices_export_filename(as_of=None) -> str:
    from datetime import datetime

    day = (as_of or datetime.utcnow()).strftime("%Y-%m-%d")
    return f"myhigh5-invoices-{day}.pdf"
