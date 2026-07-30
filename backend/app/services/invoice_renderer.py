"""HTML invoice rendering for validated deposits (browser + PDF export)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.payment import Deposit


INVOICE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "invoice": "FACTURE",
        "invoice_number": "N°",
        "date": "Date",
        "paid": "PAYÉ",
        "billed_to": "Facturé à",
        "issuer": "Émetteur",
        "origin": "Origine",
        "payment_origin": "Origine du paiement",
        "description": "Description",
        "quantity": "Quantité",
        "unit_price": "Prix unitaire",
        "total": "Total",
        "subtotal": "Sous-total",
        "vat": "TVA (0%)",
        "thank_you": "Merci pour votre confiance!",
        "payment_method": "Mode de paiement",
        "reference": "Référence",
        "online_services": "Services en ligne",
        "order_ref": "Commande",
    },
    "en": {
        "invoice": "INVOICE",
        "invoice_number": "No.",
        "date": "Date",
        "paid": "PAID",
        "billed_to": "Billed to",
        "issuer": "Issuer",
        "origin": "Origin",
        "payment_origin": "Payment origin",
        "description": "Description",
        "quantity": "Quantity",
        "unit_price": "Unit price",
        "total": "Total",
        "subtotal": "Subtotal",
        "vat": "VAT (0%)",
        "thank_you": "Thank you for your trust!",
        "payment_method": "Payment method",
        "reference": "Reference",
        "online_services": "Online services",
        "order_ref": "Order",
    },
}


def invoice_lang(lang: Optional[str]) -> str:
    code = (lang or "en").strip().lower()[:2]
    return code if code in INVOICE_TRANSLATIONS else "en"


def user_origin_label(user: Any, lang: str) -> str:
    """Geographic origin shown on invoice (country / region)."""
    if not user:
        return "—"
    parts = []
    city = getattr(user, "city", None)
    country = getattr(user, "country", None)
    region = getattr(user, "region", None)
    continent = getattr(user, "continent", None)
    if city:
        parts.append(str(city))
    if country:
        parts.append(str(country))
    elif region:
        parts.append(str(region))
    elif continent:
        parts.append(str(continent))
    return ", ".join(parts) if parts else ("Unknown" if lang == "en" else "Inconnue")


def payment_origin_label(deposit: Deposit, lang: str) -> str:
    if deposit.validated_by:
        return "Admin grant" if lang == "en" else "Octroi administrateur"
    if deposit.external_payment_id:
        return "NOWPayments"
    if deposit.tx_hash or deposit.from_address:
        return "Cryptocurrency" if lang == "en" else "Cryptomonnaie"
    return "Manual" if lang == "en" else "Manuel"


def payment_method_label(deposit: Deposit, lang: str) -> str:
    if deposit.payment_method and getattr(deposit.payment_method, "name", None):
        return str(deposit.payment_method.name)
    if deposit.crypto_currency:
        return f"Cryptocurrency ({deposit.crypto_currency})"
    if deposit.validated_by:
        return "Admin grant" if lang == "en" else "Octroi administrateur"
    return "NOWPayments" if lang == "en" else "Cryptomonnaie (NOWPayments)"


def _invoice_date(deposit: Deposit) -> str:
    dt = deposit.validated_at or deposit.created_at
    if not dt:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y")
    return str(dt)


def render_invoice_html(
    deposit: Deposit,
    *,
    billed_user: Any,
    product_name: str,
    lang: Optional[str] = "en",
    include_print_script: bool = False,
    page_break_after: bool = False,
) -> str:
    """Single invoice page — same layout for browser view and bulk PDF export."""
    user_lang = invoice_lang(lang)
    t = INVOICE_TRANSLATIONS[user_lang]
    amount = float(deposit.amount or 0)
    origin = user_origin_label(billed_user, user_lang)
    pay_origin = payment_origin_label(deposit, user_lang)
    pay_method = payment_method_label(deposit, user_lang)
    reference = deposit.external_payment_id or deposit.order_id or str(deposit.id)
    order_ref = deposit.order_id or f"MH5-{deposit.id:06d}"

    billed_name = "—"
    billed_email = "—"
    if billed_user:
        billed_name = billed_user.full_name or billed_user.username or billed_email
        billed_email = billed_user.email or "—"

    print_script = (
        "<script>window.print();</script>" if include_print_script else ""
    )
    page_break = (
        "page-break-after: always;" if page_break_after else ""
    )

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{t["invoice"]} #{deposit.id:06d}</title>
    <style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: Helvetica, Arial, sans-serif; padding: 24px; color: #333; font-size: 12px; {page_break} }}
        .invoice {{ max-width: 720px; margin: 0 auto; }}
        .header-table {{ width: 100%; border-bottom: 2px solid #1e40af; margin-bottom: 28px; padding-bottom: 16px; }}
        .logo {{ font-size: 22px; font-weight: bold; color: #1e40af; }}
        .invoice-info {{ text-align: right; }}
        .invoice-info h2 {{ font-size: 20px; color: #1e40af; margin: 0 0 4px 0; }}
        .status {{ display: inline-block; padding: 4px 12px; background: #d4edda; color: #155724; border-radius: 12px; font-size: 11px; font-weight: 600; }}
        .parties-table {{ width: 100%; margin-bottom: 28px; }}
        .party h3 {{ font-size: 10px; color: #666; text-transform: uppercase; margin: 0 0 8px 0; }}
        .party p {{ margin: 0 0 4px 0; line-height: 1.5; }}
        .items {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        .items th {{ background: #f8f9fa; padding: 10px; text-align: left; font-size: 10px; text-transform: uppercase; color: #666; border-bottom: 2px solid #e9ecef; }}
        .items td {{ padding: 12px 10px; border-bottom: 1px solid #e9ecef; }}
        .amount {{ text-align: right; }}
        .totals {{ width: 100%; margin-top: 8px; }}
        .totals td {{ padding: 6px 0; }}
        .totals .label {{ text-align: right; padding-right: 24px; color: #555; }}
        .totals .value {{ text-align: right; width: 120px; }}
        .totals .final td {{ font-size: 14px; font-weight: bold; color: #1e40af; border-top: 2px solid #1e40af; padding-top: 10px; }}
        .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e9ecef; text-align: center; color: #666; font-size: 11px; }}
        .meta {{ margin-top: 12px; font-size: 11px; color: #555; }}
    </style>
</head>
<body>
    <div class="invoice">
        <table class="header-table" cellpadding="0" cellspacing="0">
            <tr>
                <td class="logo" valign="top">MyHigh5</td>
                <td class="invoice-info" valign="top">
                    <h2>{t["invoice"]}</h2>
                    <p>{t["invoice_number"]} {deposit.id:06d}</p>
                    <p>{t["date"]}: {_invoice_date(deposit)}</p>
                    <span class="status">{t["paid"]}</span>
                </td>
            </tr>
        </table>

        <table class="parties-table" cellpadding="0" cellspacing="0">
            <tr>
                <td class="party" width="50%" valign="top">
                    <h3>{t["billed_to"]}</h3>
                    <p><strong>{_html_escape(billed_name)}</strong></p>
                    <p>{_html_escape(billed_email)}</p>
                    <p class="meta"><strong>{t["origin"]}:</strong> {_html_escape(origin)}</p>
                </td>
                <td class="party" width="50%" valign="top">
                    <h3>{t["issuer"]}</h3>
                    <p><strong>MyHigh5</strong></p>
                    <p>{t["online_services"]}</p>
                    <p>infos@myhigh5.com</p>
                </td>
            </tr>
        </table>

        <table class="items">
            <thead>
                <tr>
                    <th>{t["description"]}</th>
                    <th>{t["quantity"]}</th>
                    <th class="amount">{t["unit_price"]}</th>
                    <th class="amount">{t["total"]}</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{_html_escape(product_name)}</td>
                    <td>1</td>
                    <td class="amount">${amount:.2f}</td>
                    <td class="amount">${amount:.2f}</td>
                </tr>
            </tbody>
        </table>

        <table class="totals" align="right">
            <tr>
                <td class="label">{t["subtotal"]}:</td>
                <td class="value">${amount:.2f}</td>
            </tr>
            <tr>
                <td class="label">{t["vat"]}:</td>
                <td class="value">$0.00</td>
            </tr>
            <tr class="final">
                <td class="label">{t["total"]}:</td>
                <td class="value">${amount:.2f} {deposit.currency or "USD"}</td>
            </tr>
        </table>

        <div class="footer">
            <p>{t["thank_you"]}</p>
            <p class="meta">{t["payment_origin"]}: {_html_escape(pay_origin)}</p>
            <p class="meta">{t["payment_method"]}: {_html_escape(pay_method)}</p>
            <p class="meta">{t["reference"]}: {_html_escape(str(reference))}</p>
            <p class="meta">{t["order_ref"]}: {_html_escape(str(order_ref))}</p>
        </div>
    </div>
    {print_script}
</body>
</html>"""


def render_invoices_bulk_html(
    items: list[tuple[Deposit, Any, str]],
    *,
    lang: Optional[str] = "en",
) -> str:
    """Wrap multiple invoice pages in one HTML document for PDF merging."""
    pages = []
    for idx, (deposit, user, product_name) in enumerate(items):
        is_last = idx == len(items) - 1
        page_html = render_invoice_html(
            deposit,
            billed_user=user,
            product_name=product_name,
            lang=lang,
            include_print_script=False,
            page_break_after=not is_last,
        )
        # Strip outer html/body for concatenation
        inner = page_html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
        pages.append(inner)

    user_lang = invoice_lang(lang)
    title = "Invoices" if user_lang == "en" else "Factures"
    combined_body = "\n".join(pages)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: Helvetica, Arial, sans-serif; color: #333; font-size: 12px; margin: 0; padding: 0; }}
    </style>
</head>
<body>
{combined_body}
</body>
</html>"""


def _html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
