"""Shareable finance reports: owner picks accounts, categories, dates, expiry."""
from __future__ import annotations

import io
import secrets
import zipfile
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import vault_id
from app.routers.finance import _acct_map, _cat_map, _txn_query, inr
from app.templating import setup_templates

public_router = APIRouter(tags=["finance-reports"])
templates = setup_templates()

EXPIRY_HOURS = {
    "24h": 24,
    "1w": 24 * 7,
    "1m": 24 * 30,
    "never": None,
}


def _ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def load_report(db: Session, token: str) -> models.FinanceSharedReport:
    row = db.query(models.FinanceSharedReport).filter(models.FinanceSharedReport.token == token).first()
    if not row or row.revoked:
        raise HTTPException(404, "Report not found")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise HTTPException(410, "This report link has expired")
    return row


def report_rows(db: Session, report: models.FinanceSharedReport) -> list[dict]:
    accounts = set(_ids(report.account_ids))
    cats = set(_ids(report.category_ids))
    q = _txn_query(db, report.user_id).filter(
        models.FinanceTransaction.txn_date >= report.date_from,
        models.FinanceTransaction.txn_date <= report.date_to,
    )
    acct_map = _acct_map(db, report.user_id)
    cat_map = _cat_map(db, report.user_id)
    out = []
    for t in q.order_by(models.FinanceTransaction.txn_date.asc(), models.FinanceTransaction.created_at.asc()).all():
        if t.account_id not in accounts and (t.to_account_id or "") not in accounts:
            continue
        if cats and (t.category_id or "") not in cats:
            continue
        cat = cat_map.get(t.category_id) if t.category_id else None
        acc = acct_map.get(t.account_id)
        dest = acct_map.get(t.to_account_id) if t.to_account_id else None
        out.append({
            "id": t.id,
            "date": t.txn_date,
            "time": t.txn_time or "",
            "type": t.txn_type,
            "amount": float(t.amount or 0),
            "payee": t.payee or "",
            "notes": t.notes or "",
            "description": t.description or "",
            "category_id": t.category_id or "",
            "category": cat.name if cat else ("Transfer" if t.txn_type == "transfer" else "Uncategorised"),
            "account": acc.name if acc else "",
            "to_account": dest.name if dest else "",
            "method": t.payment_method or "",
        })
    return out


def apply_viewer_filters(rows: list[dict], *, txn_type: str | None, category_id: str | None, q: str | None) -> list[dict]:
    if txn_type in ("income", "expense", "transfer"):
        rows = [r for r in rows if r["type"] == txn_type]
    if category_id:
        rows = [r for r in rows if r["category_id"] == category_id]
    if q:
        needle = q.strip().lower()
        if needle:
            rows = [
                r for r in rows
                if needle in (r["payee"] + " " + r["notes"] + " " + r["description"] + " " + r["category"] + " " + r["account"]).lower()
            ]
    return rows


def totals(rows: list[dict]) -> dict:
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    return {"income": income, "expense": expense, "net": income - expense, "count": len(rows)}


def chart_payload(rows: list[dict]) -> dict:
    by_day: dict[str, dict] = {}
    by_cat: dict[str, float] = {}
    for r in rows:
        day = by_day.setdefault(r["date"], {"date": r["date"], "income": 0.0, "expense": 0.0})
        if r["type"] == "income":
            day["income"] += r["amount"]
        elif r["type"] == "expense":
            day["expense"] += r["amount"]
            by_cat[r["category"]] = by_cat.get(r["category"], 0.0) + r["amount"]
    days = [by_day[k] for k in sorted(by_day)]
    cats = [{"name": n, "amount": a} for n, a in sorted(by_cat.items(), key=lambda kv: -kv[1])]
    peak = 1.0
    for d in days:
        peak = max(peak, d["income"], d["expense"])
    cat_peak = cats[0]["amount"] if cats else 1.0
    return {"days": days, "categories": cats[:12], "peak": peak, "cat_peak": cat_peak or 1.0}


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def to_xlsx(rows: list[dict], title: str) -> bytes:
    headers = ["Date", "Time", "Type", "Amount", "Account", "To account", "Category", "Payee", "Description", "Notes", "Method"]
    keys = ["date", "time", "type", "amount", "account", "to_account", "category", "payee", "description", "notes", "method"]
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    def cell(col, row, value, kind="str"):
        ref = f"{_col(col)}{row}"
        if kind == "num":
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'

    lines.append('<row r="1">' + cell(1, 1, title) + "</row>")
    lines.append('<row r="2">' + "".join(cell(i + 1, 2, h) for i, h in enumerate(headers)) + "</row>")
    for ri, row in enumerate(rows, start=3):
        parts = []
        for ci, key in enumerate(keys, start=1):
            val = row[key]
            parts.append(cell(ci, ri, val, "num" if key == "amount" else "str"))
        lines.append(f'<row r="{ri}">' + "".join(parts) + "</row>")
    lines.append("</sheetData></worksheet>")
    sheet = "".join(lines).encode()
    content_types = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    wb_rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    workbook = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def create_report(
    db: Session,
    user: models.User,
    *,
    title: str,
    account_ids: list[str],
    category_ids: list[str],
    date_from: str,
    date_to: str,
    expiry: str,
) -> models.FinanceSharedReport:
    uid = vault_id(user)
    owned = {
        a.id for a in db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    }
    picked = [a for a in account_ids if a in owned]
    if not picked:
        raise HTTPException(400, "Pick at least one account")
    if not date_from or not date_to:
        raise HTTPException(400, "Pick a start and end date")
    if date_from > date_to:
        raise HTTPException(400, "Start date is after end date")
    cat_owned = {
        c.id for c in db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    }
    cats = [c for c in category_ids if c in cat_owned]
    hours = EXPIRY_HOURS.get(expiry, 24)
    expires = None if hours is None else datetime.utcnow() + timedelta(hours=hours)
    row = models.FinanceSharedReport(
        token=secrets.token_urlsafe(18),
        user_id=uid,
        title=(title or "Shared report").strip()[:255],
        account_ids=",".join(picked),
        category_ids=",".join(cats) if cats else None,
        date_from=date_from,
        date_to=date_to,
        expires_at=expires,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _public_ctx(report, rows, request: Request):
    txn_type = request.query_params.get("type") or ""
    category_id = request.query_params.get("category") or ""
    q = request.query_params.get("q") or ""
    tab = request.query_params.get("tab") or "list"
    shown = apply_viewer_filters(rows, txn_type=txn_type or None, category_id=category_id or None, q=q or None)
    cats = {}
    for r in rows:
        if r["category_id"]:
            cats[r["category_id"]] = r["category"]
    return {
        "request": request,
        "report": report,
        "rows": shown,
        "all_count": len(rows),
        "totals": totals(shown),
        "charts": chart_payload(shown),
        "categories": [{"id": i, "name": n} for i, n in sorted(cats.items(), key=lambda kv: kv[1].lower())],
        "txn_type": txn_type,
        "category_id": category_id,
        "q": q,
        "tab": tab if tab in ("list", "charts") else "list",
        "inr": inr,
        "expired_label": report.expires_at.strftime("%d %b %Y %H:%M UTC") if report.expires_at else "Never",
    }


@public_router.get("/r/{token}", response_class=HTMLResponse)
def view_shared_report(token: str, request: Request, db: Session = Depends(get_db)):
    report = load_report(db, token)
    rows = report_rows(db, report)
    return templates.TemplateResponse("finance_report_public.html", _public_ctx(report, rows, request))


@public_router.get("/r/{token}/excel")
def download_shared_report(token: str, request: Request, db: Session = Depends(get_db)):
    report = load_report(db, token)
    rows = report_rows(db, report)
    shown = apply_viewer_filters(
        rows,
        txn_type=request.query_params.get("type") or None,
        category_id=request.query_params.get("category") or None,
        q=request.query_params.get("q") or None,
    )
    data = to_xlsx(shown, f"{report.title} {report.date_from} to {report.date_to}")
    filename = "report.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
