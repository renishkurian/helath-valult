"""Full-vault backup: export and restore every module for the signed-in owner."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, crypto, schemas
from app.config import settings
from app.deps import get_current_user, require_owner, vault_id
from app.extract import extract_text, parse_lab_readings

router = APIRouter(prefix="/backup", tags=["backup"])

MANIFEST_VERSION = 2


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def _dec(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _write_enc_file(zf: zipfile.ZipFile, arcname: str, rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    enc_path = settings.STORAGE_DIR / rel_path
    if not enc_path.exists():
        return None
    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    zf.writestr(arcname, plain)
    return arcname


def build_vault_backup(
    db: Session,
    user: models.User,
    *,
    person_id: str | None = None,
) -> bytes:
    """Zip every module for this vault (or one person's health data only)."""
    owner = vault_id(user)
    full = not person_id
    manifest: dict[str, Any] = {
        "exported_at": datetime.utcnow().isoformat(),
        "manifest_version": MANIFEST_VERSION,
        "modules": ["health"],
        "people": [],
        "locker": [],
        "passwords": {"folders": [], "items": []},
        "finance": {},
        "urls": {},
        "shopping": {},
        "expense_analyser": {},
        "ai": {},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        q = db.query(models.Person).filter(models.Person.user_id == owner)
        if person_id:
            q = q.filter(models.Person.id == person_id)
        people = q.all()
        for person in people:
            manifest["people"].append(_export_person(db, zf, person))

        if full:
            locker_items = (
                db.query(models.LockerItem)
                .filter(models.LockerItem.user_id == owner)
                .all()
            )
            for item in locker_items:
                manifest["locker"].append(_export_locker_item(zf, item))
            if locker_items:
                manifest["modules"].append("locker")

            manifest["passwords"] = _export_passwords(db, owner)
            if manifest["passwords"]["folders"] or manifest["passwords"]["items"]:
                manifest["modules"].append("passwords")

            manifest["finance"] = _export_finance(db, owner)
            if any(manifest["finance"].values()):
                manifest["modules"].append("finance")

            manifest["urls"] = _export_urls(db, owner)
            if any(manifest["urls"].values()):
                manifest["modules"].append("urls")

            manifest["shopping"] = _export_shopping(db, zf, owner)
            if any(manifest["shopping"].values()):
                manifest["modules"].append("shopping")

            manifest["expense_analyser"] = _export_expense_analyser(db, owner)
            if any(v for v in manifest["expense_analyser"].values() if v):
                manifest["modules"].append("expense_analyser")

            manifest["ai"] = _export_ai(db, owner)
            if any(manifest["ai"].values()):
                manifest["modules"].append("ai")

        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=_json_default))
    return buf.getvalue()


def _build_zip(people, locker_items=None, db: Session | None = None, user: models.User | None = None) -> bytes:
    """Prefer build_vault_backup(db, user). Legacy signature kept for older callers."""
    if db is not None and user is not None:
        return build_vault_backup(db, user)
    manifest = {
        "exported_at": datetime.utcnow().isoformat(),
        "manifest_version": 1,
        "people": [],
        "locker": [],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for person in people or []:
            # Legacy path has no Session — skip care tables that need queries
            manifest["people"].append(_export_person(None, zf, person))
        for item in locker_items or []:
            manifest["locker"].append(_export_locker_item(zf, item))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=_json_default))
    return buf.getvalue()


def _export_person(db: Session | None, zf: zipfile.ZipFile, person: models.Person) -> dict:
    person_entry: dict[str, Any] = {
        "name": person.name,
        "relation": person.relation.value if person.relation else None,
        "dob": person.dob,
        "blood_group": person.blood_group,
        "allergies": person.allergies,
        "conditions": person.conditions,
        "cards": [],
        "documents": [],
        "reminders": [],
        "medicines": [],
        "vaccinations": [],
        "visits": [],
        "claims": [],
        "uhids": [],
        "lab_readings": [],
        "growth": [],
    }
    for card in person.cards or []:
        person_entry["cards"].append({
            "hospital_name": card.hospital_name, "ward": card.ward, "blood_group": card.blood_group,
            "valid_from": card.valid_from, "valid_till": card.valid_till,
            "patient_id": crypto.decrypt_text(card.patient_id_enc),
            "notes": crypto.decrypt_text(card.notes_enc),
        })
    for doc in person.documents or []:
        doc_folder = f"{person.name}/{doc.category.value}/{doc.id}"
        file_names = []
        for f in doc.files or []:
            arc = _write_enc_file(zf, f"{doc_folder}/{f.original_filename}", f.file_path)
            if arc:
                file_names.append(arc)
        person_entry["documents"].append({
            "title": doc.title, "category": doc.category.value, "custom_category": doc.custom_category,
            "hospital_name": doc.hospital_name, "doc_date": doc.doc_date, "expiry_date": doc.expiry_date,
            "tags": doc.tags, "notes": crypto.decrypt_text(doc.notes_enc),
            "extracted_text": doc.extracted_text, "amount": doc.amount,
            "files": file_names,
        })
    for rem in person.reminders or []:
        person_entry["reminders"].append({
            "title": rem.title, "description": rem.description,
            "remind_at": rem.remind_at,
            "repeat_rule": rem.repeat_rule.value if rem.repeat_rule else "none",
            "is_active": rem.is_active,
        })
    if db is not None:
        for m in db.query(models.Medicine).filter(models.Medicine.person_id == person.id).all():
            person_entry["medicines"].append({
                "name": m.name, "dose": m.dose, "timing": m.timing,
                "remaining": m.remaining, "refill_at": m.refill_at,
            })
        for v in db.query(models.VaccinationRecord).filter(models.VaccinationRecord.person_id == person.id).all():
            person_entry["vaccinations"].append({
                "vaccine_name": v.vaccine_name, "given_on": v.given_on, "next_due": v.next_due,
            })
        for v in db.query(models.Visit).filter(models.Visit.person_id == person.id).all():
            person_entry["visits"].append({
                "hospital_name": v.hospital_name, "doctor_name": v.doctor_name,
                "visit_date": v.visit_date, "reason": v.reason,
            })
        for c in db.query(models.Claim).filter(models.Claim.person_id == person.id).all():
            person_entry["claims"].append({
                "insurer": c.insurer, "status": c.status, "amount": c.amount,
                "claim_number": c.claim_number, "notes": c.notes,
            })
        for u in db.query(models.HospitalUhid).filter(models.HospitalUhid.person_id == person.id).all():
            person_entry["uhids"].append({"hospital_name": u.hospital_name, "uhid": u.uhid})
        for r in db.query(models.LabReading).filter(models.LabReading.person_id == person.id).all():
            person_entry["lab_readings"].append({
                "metric": r.metric, "value": r.value, "unit": r.unit, "measured_at": r.measured_at,
            })
        for g in db.query(models.GrowthReading).filter(models.GrowthReading.person_id == person.id).all():
            person_entry["growth"].append({
                "measured_at": g.measured_at,
                "height_cm": getattr(g, "height_cm", None),
                "weight_kg": getattr(g, "weight_kg", None),
            })
    return person_entry


def _export_locker_item(zf: zipfile.ZipFile, item: models.LockerItem) -> dict:
    folder = f"locker/{item.doc_type}/{item.id}"
    file_names = []
    for f in item.files or []:
        arc = _write_enc_file(zf, f"{folder}/{f.original_filename}", f.file_path)
        if arc:
            file_names.append(arc)
    return {
        "title": item.title, "doc_type": item.doc_type, "custom_type": item.custom_type,
        "holder_name": item.holder_name, "issuer": item.issuer,
        "id_number": crypto.decrypt_text(item.id_number_enc),
        "issued_on": item.issued_on, "expiry_date": item.expiry_date,
        "tags": item.tags, "notes": crypto.decrypt_text(item.notes_enc),
        "files": file_names,
    }


def _export_passwords(db: Session, owner: str) -> dict:
    folders = db.query(models.VaultFolder).filter(models.VaultFolder.user_id == owner).all()
    items = db.query(models.VaultItem).filter(models.VaultItem.user_id == owner).all()
    folder_names = {f.id: f.name for f in folders}
    return {
        "folders": [{"name": f.name} for f in folders],
        "items": [{
            "folder": folder_names.get(it.folder_id),
            "item_type": it.item_type,
            "name": it.name,
            "favorite": bool(it.favorite),
            "deleted_at": it.deleted_at,
            "username": it.username,
            "password": crypto.decrypt_text(it.password_enc),
            "totp_secret": crypto.decrypt_text(it.totp_secret_enc),
            "uris": it.uris,
            "notes": crypto.decrypt_text(it.notes_enc),
            "cardholder_name": it.cardholder_name,
            "card_brand": it.card_brand,
            "card_number": crypto.decrypt_text(it.card_number_enc),
            "card_exp_month": it.card_exp_month,
            "card_exp_year": it.card_exp_year,
            "card_cvv": crypto.decrypt_text(it.card_cvv_enc),
            "identity_title": it.identity_title,
            "first_name": it.first_name, "middle_name": it.middle_name, "last_name": it.last_name,
            "email": it.email, "phone": it.phone,
            "address1": it.address1, "address2": it.address2,
            "city": it.city, "state": it.state, "postal_code": it.postal_code, "country": it.country,
            "ssn": crypto.decrypt_text(it.ssn_enc),
            "license_number": crypto.decrypt_text(it.license_number_enc),
            "passport_number": crypto.decrypt_text(it.passport_number_enc),
        } for it in items],
    }


def _export_finance(db: Session, owner: str) -> dict:
    accounts = db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == owner).all()
    cats = db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == owner).all()
    txns = db.query(models.FinanceTransaction).filter(models.FinanceTransaction.user_id == owner).all()
    budgets = db.query(models.FinanceBudget).filter(models.FinanceBudget.user_id == owner).all()
    emis = db.query(models.FinanceEmi).filter(models.FinanceEmi.user_id == owner).all()
    recurring = db.query(models.FinanceRecurring).filter(models.FinanceRecurring.user_id == owner).all()
    rules = db.query(models.FinanceRule).filter(models.FinanceRule.user_id == owner).all()
    messages = db.query(models.FinanceMessage).filter(models.FinanceMessage.user_id == owner).all()
    acct_name = {a.id: a.name for a in accounts}
    cat_name = {c.id: c.name for c in cats}
    return {
        "accounts": [{
            "name": a.name, "account_type": a.account_type, "institution": a.institution,
            "last4": a.last4, "currency": getattr(a, "currency", None) or "INR",
            "opening_balance": _dec(getattr(a, "opening_balance", None)),
            "credit_limit": _dec(a.credit_limit), "archived": bool(a.archived),
            "notes": getattr(a, "notes", None),
        } for a in accounts],
        "categories": [{
            "name": c.name, "kind": c.kind, "parent_name": cat_name.get(c.parent_id),
            "icon": getattr(c, "icon", None), "color": getattr(c, "color", None),
        } for c in cats],
        "transactions": [{
            "account": acct_name.get(t.account_id),
            "category": cat_name.get(t.category_id),
            "txn_type": t.txn_type, "amount": _dec(t.amount), "txn_date": t.txn_date,
            "payee": t.payee, "notes": t.notes,
            "description": t.description,
            "payment_method": t.payment_method,
            "transfer_account": acct_name.get(t.to_account_id),
        } for t in txns],
        "budgets": [{
            "category": cat_name.get(b.category_id), "year_month": b.year_month,
            "amount": _dec(b.amount),
        } for b in budgets],
        "emis": [{
            "name": e.name, "kind": e.kind, "amount": _dec(e.amount),
            "account": acct_name.get(e.account_id), "next_due": e.next_due,
            "active": bool(e.active), "notes": e.notes,
            "start_date": e.start_date, "end_date": e.end_date,
            "day_of_month": e.day_of_month,
        } for e in emis],
        "recurring": [{
            "name": r.payee or "Recurring", "amount": _dec(r.amount),
            "account": acct_name.get(r.account_id),
            "category": cat_name.get(r.category_id), "txn_type": r.txn_type,
            "next_due": r.next_due, "active": bool(r.active), "notes": r.notes,
            "payee": r.payee, "frequency": r.frequency,
        } for r in recurring],
        "rules": [{
            "pattern": r.match_text, "payee": r.payee,
            "category": cat_name.get(r.category_id),
            "txn_type": r.txn_type,
        } for r in rules],
        "messages": [{
            "raw_text": m.raw_text,
            "direction": m.direction, "amount": _dec(m.amount), "payee": m.payee,
            "suggested_category": m.suggested_category, "payment_method": m.payment_method,
            "provider_used": getattr(m, "provider_used", None), "status": getattr(m, "status", None),
            "txn_date": m.txn_date,
        } for m in messages],
    }


def _export_urls(db: Session, owner: str) -> dict:
    cats = db.query(models.UrlCategory).filter(models.UrlCategory.user_id == owner).all()
    tags = db.query(models.UrlTag).filter(models.UrlTag.user_id == owner).all()
    items = db.query(models.UrlItem).filter(models.UrlItem.user_id == owner).all()
    cat_name = {c.id: c.name for c in cats}
    return {
        "categories": [{"name": c.name, "color": getattr(c, "color", None)} for c in cats],
        "tags": [{"name": t.name} for t in tags],
        "items": [{
            "title": u.title, "url": u.url,
            "notes": crypto.decrypt_text(u.notes_enc) if u.notes_enc else None,
            "category": cat_name.get(u.category_id), "favorite": bool(u.favorite),
            "tag_names": [t.name for t in (u.tags or [])],
            "og_title": u.og_title, "og_description": u.og_description,
            "og_image": u.og_image, "og_site_name": u.og_site_name,
            "favicon_url": u.favicon_url,
        } for u in items],
    }


def _export_shopping(db: Session, zf: zipfile.ZipFile, owner: str) -> dict:
    lists = db.query(models.ShopList).filter(models.ShopList.user_id == owner).all()
    contacts = db.query(models.ShopContact).filter(models.ShopContact.user_id == owner).all()
    pdf_pw = db.query(models.ShopPdfPassword).filter(models.ShopPdfPassword.user_id == owner).all()

    dict_out = []
    for d in db.query(models.ShopDictItem).all():
        if getattr(d, "source", None) == "seed":
            continue
        dict_out.append({
            "key": d.key, "english": d.english, "malayalam": d.malayalam,
            "emoji": d.emoji, "category": d.category, "source": d.source,
        })

    list_out = []
    for lst in lists:
        receipts = []
        for rec in lst.receipts or []:
            safe = (rec.original_name or "receipt").replace("/", "_")
            arc = f"shopping/{lst.id}/receipts/{rec.id}_{safe}"
            written = _write_enc_file(zf, arc, rec.image_path)
            receipts.append({
                "original_name": rec.original_name,
                "image_mime": rec.image_mime,
                "file": written,
                "created_at": rec.created_at,
            })
        shares = [{
            "token": s.token, "expires_at": s.expires_at, "use_count": s.use_count,
            "created_at": s.created_at,
        } for s in (lst.shares or [])]
        items = [{
            "name": i.name, "quantity": _dec(i.quantity), "unit": i.unit,
            "price": _dec(i.price), "checked": bool(i.checked), "emoji": i.emoji,
            "category": i.category, "notes": i.notes, "status": i.status,
            "guest_name": i.guest_name, "created_at": i.created_at, "updated_at": i.updated_at,
        } for i in (lst.items or [])]
        list_out.append({
            "name": lst.name, "description": lst.description,
            "completed": bool(lst.completed), "total_amount": _dec(lst.total_amount),
            "created_at": lst.created_at, "completed_at": lst.completed_at,
            "deleted_at": lst.deleted_at, "blocked_uids": lst.blocked_uids,
            "items": items, "receipts": receipts, "shares": shares,
        })

    return {
        "lists": list_out,
        "contacts": [{
            "name": c.name, "email": c.email, "phone": c.phone, "relation": c.relation,
        } for c in contacts],
        "pdf_passwords": [{
            "identifier": p.identifier,
            "password": crypto.decrypt_text(p.password_enc),
            "account_type": p.account_type,
            "last_4_digits": p.last_4_digits,
        } for p in pdf_pw],
        "dict": dict_out,
        "catalog": [{
            "english": c.english, "malayalam": c.malayalam, "emoji": c.emoji,
            "category": c.category, "scope": c.scope, "aliases": c.aliases,
        } for c in db.query(models.ShopCatalogItem).filter(
            models.ShopCatalogItem.user_id == owner
        ).all()],
    }


def _export_expense_analyser(db: Session, owner: str) -> dict:
    items = (
        db.query(models.ExpenseAnalyserItem)
        .filter(models.ExpenseAnalyserItem.user_id == owner)
        .order_by(models.ExpenseAnalyserItem.created_at.desc())
        .limit(5000)
        .all()
    )
    logs = (
        db.query(models.ExpenseAnalyserSyncLog)
        .filter(models.ExpenseAnalyserSyncLog.user_id == owner)
        .order_by(models.ExpenseAnalyserSyncLog.finished_at.desc())
        .limit(200)
        .all()
    )
    conn = (
        db.query(models.ExpenseAnalyserConnection)
        .filter(models.ExpenseAnalyserConnection.user_id == owner)
        .first()
    )
    return {
        "connection": ({
            "connected_email": conn.connected_email,
            "enabled": bool(conn.enabled),
            "sync_query": getattr(conn, "sync_query", None),
        } if conn else None),
        "items": [{
            "gmail_message_id": it.gmail_message_id,
            "subject": it.subject, "from_addr": it.from_addr,
            "received_at": it.received_at, "txn_date": it.txn_date,
            "direction": it.direction, "amount": _dec(it.amount),
            "payee": it.payee, "suggested_category": it.suggested_category,
            "payment_method": it.payment_method, "status": it.status,
            "confidence": it.confidence,
            "account_hint": None,
            "raw_text": crypto.decrypt_text(it.raw_text_enc) if it.raw_text_enc else None,
        } for it in items],
        "sync_logs": [{
            "trigger": lg.trigger,
            "ok": bool(lg.ok),
            "error": lg.error,
            "fetched": lg.fetched,
            "created": lg.created,
            "started_at": lg.started_at,
            "finished_at": lg.finished_at,
        } for lg in logs],
    }


def _export_ai(db: Session, owner: str) -> dict:
    providers = db.query(models.AiProvider).filter(models.AiProvider.user_id == owner).all()
    threads = (
        db.query(models.AiChatThread)
        .filter(models.AiChatThread.user_id == owner)
        .order_by(models.AiChatThread.updated_at.desc())
        .limit(50)
        .all()
    )
    thread_out = []
    for t in threads:
        msgs = (
            db.query(models.AiChatMessage)
            .filter(models.AiChatMessage.thread_id == t.id)
            .order_by(models.AiChatMessage.created_at)
            .all()
        )
        thread_out.append({
            "title": t.title,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "messages": [{
                "role": m.role,
                "content": crypto.decrypt_text(m.content_enc) or "",
                "created_at": m.created_at,
            } for m in msgs],
        })
    return {
        "providers": [{
            "name": p.name, "kind": p.kind, "model": p.model,
            "base_url": p.base_url, "is_default": bool(p.is_default),
            "api_key": crypto.decrypt_text(p.api_key_enc),
        } for p in providers],
        "threads": thread_out,
    }


def _parse_dt(val):
    if val is None or isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", ""))
        except ValueError:
            return None
    return None


def _restore_modules(db: Session, owner: str, zf: zipfile.ZipFile, manifest: dict) -> dict:
    restored = {
        "people": 0, "documents": 0, "cards": 0,
        "locker": 0, "passwords": 0, "finance_accounts": 0, "finance_txns": 0,
        "urls": 0, "shop_lists": 0, "shop_items": 0, "shop_catalog": 0, "ea_items": 0, "ai_threads": 0,
    }
    for person_entry in manifest.get("people", []):
        _restore_person(db, owner, zf, person_entry, restored)
    for item in manifest.get("locker", []):
        _restore_locker(db, owner, zf, item, restored)
    pw = manifest.get("passwords") or {}
    if pw:
        _restore_passwords(db, owner, pw, restored)
    fin = manifest.get("finance") or {}
    if fin:
        _restore_finance(db, owner, fin, restored)
    urls = manifest.get("urls") or {}
    if urls:
        _restore_urls(db, owner, urls, restored)
    shop = manifest.get("shopping") or {}
    if shop:
        _restore_shopping(db, owner, zf, shop, restored)
    ea = manifest.get("expense_analyser") or {}
    if ea:
        _restore_expense_analyser(db, owner, ea, restored)
    ai = manifest.get("ai") or {}
    if ai:
        _restore_ai(db, owner, ai, restored)
    db.commit()
    return restored


def _get_or_create_person(db: Session, owner: str, person_entry: dict, restored: dict) -> models.Person:
    existing = (
        db.query(models.Person)
        .filter(models.Person.user_id == owner, models.Person.name == person_entry.get("name"))
        .first()
    )
    if existing:
        return existing
    rel = person_entry.get("relation") or "other"
    try:
        relation = models.Relation(rel)
    except ValueError:
        relation = models.Relation.other
    if relation == models.Relation.self_:
        person = (
            db.query(models.Person)
            .filter(models.Person.user_id == owner, models.Person.relation == models.Relation.self_)
            .first()
        )
        if person:
            return person
    person = models.Person(
        user_id=owner, name=person_entry["name"], relation=relation,
        dob=person_entry.get("dob"), blood_group=person_entry.get("blood_group"),
        allergies=person_entry.get("allergies"), conditions=person_entry.get("conditions"),
    )
    db.add(person)
    db.flush()
    restored["people"] += 1
    return person


def _restore_person(db: Session, owner: str, zf: zipfile.ZipFile, person_entry: dict, restored: dict) -> None:
    person = _get_or_create_person(db, owner, person_entry, restored)

    for card in person_entry.get("cards", []):
        db.add(models.HospitalCard(
            person_id=person.id,
            hospital_name=card.get("hospital_name") or "Unknown",
            ward=card.get("ward"),
            blood_group=card.get("blood_group"),
            valid_from=card.get("valid_from"),
            valid_till=card.get("valid_till"),
            patient_id_enc=crypto.encrypt_text(card.get("patient_id")),
            notes_enc=crypto.encrypt_text(card.get("notes")),
        ))
        restored["cards"] += 1

    person_dir = settings.STORAGE_DIR / owner / person.id
    person_dir.mkdir(parents=True, exist_ok=True)

    for doc_entry in person_entry.get("documents", []):
        try:
            cat = models.DocCategory(doc_entry.get("category") or "other")
        except ValueError:
            cat = models.DocCategory.other
        doc = models.Document(
            person_id=person.id,
            category=cat,
            custom_category=doc_entry.get("custom_category"),
            title=doc_entry.get("title") or "Restored document",
            hospital_name=doc_entry.get("hospital_name"),
            doc_date=doc_entry.get("doc_date"),
            expiry_date=doc_entry.get("expiry_date"),
            tags=doc_entry.get("tags"),
            notes_enc=crypto.encrypt_text(doc_entry.get("notes")),
            extracted_text=doc_entry.get("extracted_text"),
            file_path="",
        )
        if hasattr(doc, "amount") and doc_entry.get("amount") is not None:
            doc.amount = doc_entry.get("amount")
        db.add(doc)
        db.flush()
        for idx, arcname in enumerate(doc_entry.get("files") or []):
            try:
                raw = zf.read(arcname)
            except KeyError:
                continue
            enc_path = person_dir / f"{doc.id}_{idx}.enc"
            enc_path.write_bytes(crypto.encrypt_bytes(raw))
            db.add(models.DocumentFile(
                document_id=doc.id,
                original_filename=arcname.split("/")[-1],
                file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
                file_type="application/octet-stream",
                file_size=len(raw),
            ))
            if not doc.extracted_text:
                text = extract_text(raw, None, arcname)
                if text:
                    doc.extracted_text = (doc.extracted_text or "") + "\n" + text
        if doc.extracted_text:
            for reading in parse_lab_readings(doc.extracted_text):
                db.add(models.LabReading(
                    person_id=person.id, document_id=doc.id,
                    metric=reading["metric"], value=reading["value"],
                    unit=reading["unit"], measured_at=doc.doc_date,
                ))
        restored["documents"] += 1

    for rem in person_entry.get("reminders", []):
        try:
            rule = models.RepeatRule(rem.get("repeat_rule") or "none")
        except ValueError:
            rule = models.RepeatRule.none
        remind_at = _parse_dt(rem.get("remind_at")) or datetime.utcnow()
        db.add(models.Reminder(
            person_id=person.id,
            title=rem.get("title") or "Reminder",
            description=rem.get("description"),
            remind_at=remind_at,
            repeat_rule=rule,
            is_active=bool(rem.get("is_active", True)),
        ))

    for m in person_entry.get("medicines", []):
        db.add(models.Medicine(
            person_id=person.id, name=m.get("name") or "Medicine",
            dose=m.get("dose"), timing=m.get("timing"),
            remaining=m.get("remaining"), refill_at=m.get("refill_at"),
        ))
    for v in person_entry.get("vaccinations", []):
        db.add(models.VaccinationRecord(
            person_id=person.id, vaccine_name=v.get("vaccine_name") or "Vaccine",
            given_on=v.get("given_on"), next_due=v.get("next_due"),
        ))
    for v in person_entry.get("visits", []):
        db.add(models.Visit(
            person_id=person.id, hospital_name=v.get("hospital_name"),
            doctor_name=v.get("doctor_name"), visit_date=v.get("visit_date"),
            reason=v.get("reason"),
        ))
    for c in person_entry.get("claims", []):
        db.add(models.Claim(
            person_id=person.id, insurer=c.get("insurer"), status=c.get("status"),
            amount=c.get("amount"), claim_number=c.get("claim_number"),
        ))
    for u in person_entry.get("uhids", []):
        if u.get("hospital_name") and u.get("uhid"):
            db.add(models.HospitalUhid(
                person_id=person.id, hospital_name=u["hospital_name"], uhid=u["uhid"],
            ))
    for r in person_entry.get("lab_readings", []):
        if r.get("metric"):
            db.add(models.LabReading(
                person_id=person.id, metric=r["metric"], value=r.get("value"),
                unit=r.get("unit"), measured_at=r.get("measured_at"),
            ))
    for g in person_entry.get("growth", []):
        kwargs = {"person_id": person.id, "measured_at": g.get("measured_at")}
        if hasattr(models.GrowthReading, "height_cm"):
            kwargs["height_cm"] = g.get("height_cm")
            kwargs["weight_kg"] = g.get("weight_kg")
        db.add(models.GrowthReading(**kwargs))


def _restore_locker(db: Session, owner: str, zf: zipfile.ZipFile, item: dict, restored: dict) -> None:
    row = models.LockerItem(
        user_id=owner,
        title=item.get("title") or "Restored",
        doc_type=item.get("doc_type") or "other",
        custom_type=item.get("custom_type"),
        holder_name=item.get("holder_name"),
        issuer=item.get("issuer"),
        id_number_enc=crypto.encrypt_text(item.get("id_number")),
        issued_on=item.get("issued_on"),
        expiry_date=item.get("expiry_date"),
        tags=item.get("tags"),
        notes_enc=crypto.encrypt_text(item.get("notes")),
    )
    db.add(row)
    db.flush()
    dest_dir = settings.STORAGE_DIR / owner / "locker"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for idx, arcname in enumerate(item.get("files") or []):
        try:
            raw = zf.read(arcname)
        except KeyError:
            continue
        enc_path = dest_dir / f"{row.id}_{idx}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        db.add(models.LockerFile(
            item_id=row.id,
            original_filename=arcname.split("/")[-1],
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type="application/octet-stream",
            file_size=len(raw),
        ))
    restored["locker"] += 1


def _restore_passwords(db: Session, owner: str, pw: dict, restored: dict) -> None:
    folder_ids: dict[str, str] = {}
    for f in pw.get("folders") or []:
        name = (f.get("name") or "").strip()
        if not name:
            continue
        existing = (
            db.query(models.VaultFolder)
            .filter(models.VaultFolder.user_id == owner, models.VaultFolder.name == name)
            .first()
        )
        if existing:
            folder_ids[name] = existing.id
            continue
        row = models.VaultFolder(user_id=owner, name=name)
        db.add(row)
        db.flush()
        folder_ids[name] = row.id
    for it in pw.get("items") or []:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        exists = (
            db.query(models.VaultItem)
            .filter(
                models.VaultItem.user_id == owner,
                models.VaultItem.name == name,
                models.VaultItem.item_type == (it.get("item_type") or "login"),
                models.VaultItem.deleted_at.is_(None),
            )
            .first()
        )
        if exists:
            continue
        folder_id = folder_ids.get(it.get("folder") or "")
        row = models.VaultItem(
            user_id=owner, folder_id=folder_id or None,
            item_type=it.get("item_type") or "login", name=name,
            favorite=bool(it.get("favorite")),
            deleted_at=_parse_dt(it.get("deleted_at")),
            username=it.get("username"),
            password_enc=crypto.encrypt_text(it.get("password")),
            totp_secret_enc=crypto.encrypt_text(it.get("totp_secret")),
            uris=it.get("uris"),
            notes_enc=crypto.encrypt_text(it.get("notes")),
            cardholder_name=it.get("cardholder_name"),
            card_brand=it.get("card_brand"),
            card_number_enc=crypto.encrypt_text(it.get("card_number")),
            card_exp_month=it.get("card_exp_month"),
            card_exp_year=it.get("card_exp_year"),
            card_cvv_enc=crypto.encrypt_text(it.get("card_cvv")),
            identity_title=it.get("identity_title"),
            first_name=it.get("first_name"), middle_name=it.get("middle_name"),
            last_name=it.get("last_name"), email=it.get("email"), phone=it.get("phone"),
            address1=it.get("address1"), address2=it.get("address2"),
            city=it.get("city"), state=it.get("state"),
            postal_code=it.get("postal_code"), country=it.get("country"),
            ssn_enc=crypto.encrypt_text(it.get("ssn")),
            license_number_enc=crypto.encrypt_text(it.get("license_number")),
            passport_number_enc=crypto.encrypt_text(it.get("passport_number")),
        )
        db.add(row)
        restored["passwords"] += 1


def _restore_finance(db: Session, owner: str, fin: dict, restored: dict) -> None:
    acct_ids: dict[str, str] = {}
    for a in fin.get("accounts") or []:
        name = (a.get("name") or "").strip()
        if not name:
            continue
        existing = (
            db.query(models.FinanceAccount)
            .filter(models.FinanceAccount.user_id == owner, models.FinanceAccount.name == name)
            .first()
        )
        if existing:
            acct_ids[name] = existing.id
            continue
        kwargs = dict(
            user_id=owner, name=name,
            account_type=a.get("account_type") or "cash",
            institution=a.get("institution"), last4=a.get("last4"),
            credit_limit=Decimal(str(a["credit_limit"])) if a.get("credit_limit") is not None else None,
            archived=bool(a.get("archived")),
        )
        row = models.FinanceAccount(**{k: v for k, v in kwargs.items() if hasattr(models.FinanceAccount, k)})
        db.add(row)
        db.flush()
        acct_ids[name] = row.id
        restored["finance_accounts"] += 1

    cat_ids: dict[str, str] = {}
    pending = list(fin.get("categories") or [])
    for _ in range(3):
        left = []
        for c in pending:
            name = (c.get("name") or "").strip()
            if not name:
                continue
            kind = c.get("kind") or "expense"
            key = f"{kind}:{name}"
            if key in cat_ids:
                continue
            parent_name = c.get("parent_name")
            parent_id = None
            if parent_name:
                parent_id = cat_ids.get(f"{kind}:{parent_name}")
                if parent_id is None:
                    left.append(c)
                    continue
            existing = (
                db.query(models.FinanceCategory)
                .filter(
                    models.FinanceCategory.user_id == owner,
                    models.FinanceCategory.name == name,
                    models.FinanceCategory.kind == kind,
                )
                .first()
            )
            if existing:
                cat_ids[key] = existing.id
                continue
            row = models.FinanceCategory(
                user_id=owner, name=name, kind=kind, parent_id=parent_id,
            )
            db.add(row)
            db.flush()
            cat_ids[key] = row.id
        pending = left
        if not pending:
            break

    for t in fin.get("transactions") or []:
        acct_id = acct_ids.get(t.get("account") or "")
        if not acct_id:
            continue
        cat_id = None
        if t.get("category"):
            cat_id = cat_ids.get(f"expense:{t['category']}") or cat_ids.get(f"income:{t['category']}")
        amount = t.get("amount")
        txn_date = t.get("txn_date")
        payee = t.get("payee")
        dup = (
            db.query(models.FinanceTransaction)
            .filter(
                models.FinanceTransaction.user_id == owner,
                models.FinanceTransaction.account_id == acct_id,
                models.FinanceTransaction.txn_date == txn_date,
                models.FinanceTransaction.amount == Decimal(str(amount or 0)),
                models.FinanceTransaction.payee == payee,
            )
            .first()
        )
        if dup:
            continue
        db.add(models.FinanceTransaction(
            user_id=owner, account_id=acct_id, category_id=cat_id,
            txn_type=t.get("txn_type") or "expense",
            amount=Decimal(str(amount or 0)),
            txn_date=txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
            payee=payee, notes=t.get("notes"),
            payment_method=t.get("payment_method"),
        ))
        restored["finance_txns"] += 1


def _restore_urls(db: Session, owner: str, urls: dict, restored: dict) -> None:
    cat_ids: dict[str, str] = {}
    for c in urls.get("categories") or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        existing = (
            db.query(models.UrlCategory)
            .filter(models.UrlCategory.user_id == owner, models.UrlCategory.name == name)
            .first()
        )
        if existing:
            cat_ids[name] = existing.id
            continue
        row = models.UrlCategory(user_id=owner, name=name)
        db.add(row)
        db.flush()
        cat_ids[name] = row.id
    for t in urls.get("tags") or []:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        exists = (
            db.query(models.UrlTag)
            .filter(models.UrlTag.user_id == owner, models.UrlTag.name == name)
            .first()
        )
        if not exists:
            db.add(models.UrlTag(user_id=owner, name=name))
    for u in urls.get("items") or []:
        title = (u.get("title") or "").strip()
        url = (u.get("url") or "").strip()
        if not title or not url:
            continue
        exists = (
            db.query(models.UrlItem)
            .filter(models.UrlItem.user_id == owner, models.UrlItem.url == url)
            .first()
        )
        if exists:
            continue
        db.add(models.UrlItem(
            user_id=owner, title=title, url=url,
            notes_enc=crypto.encrypt_text(u.get("notes")),
            category_id=cat_ids.get(u.get("category") or "") or None,
            favorite=bool(u.get("favorite")),
            og_title=u.get("og_title"), og_description=u.get("og_description"),
            og_image=u.get("og_image"), og_site_name=u.get("og_site_name"),
            favicon_url=u.get("favicon_url"),
        ))
        restored["urls"] += 1


def _restore_shopping(db: Session, owner: str, zf: zipfile.ZipFile, shop: dict, restored: dict) -> None:
    import secrets as sec
    for c in shop.get("contacts") or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        exists = (
            db.query(models.ShopContact)
            .filter(models.ShopContact.user_id == owner, models.ShopContact.name == name)
            .first()
        )
        if exists:
            continue
        db.add(models.ShopContact(
            user_id=owner, name=name, email=c.get("email"),
            phone=c.get("phone"), relation=c.get("relation"),
        ))
    for p in shop.get("pdf_passwords") or []:
        ident = (p.get("identifier") or "").strip()
        if not ident or not p.get("password"):
            continue
        exists = (
            db.query(models.ShopPdfPassword)
            .filter(models.ShopPdfPassword.user_id == owner, models.ShopPdfPassword.identifier == ident)
            .first()
        )
        if exists:
            continue
        db.add(models.ShopPdfPassword(
            user_id=owner, identifier=ident,
            password_enc=crypto.encrypt_text(p.get("password")),
            account_type=p.get("account_type") or "bank",
            last_4_digits=p.get("last_4_digits"),
        ))
    for d in shop.get("dict") or []:
        key = (d.get("key") or "").strip().lower()
        if not key:
            continue
        exists = db.query(models.ShopDictItem).filter(models.ShopDictItem.key == key).first()
        if exists:
            continue
        db.add(models.ShopDictItem(
            key=key, english=d.get("english") or key.title(),
            malayalam=d.get("malayalam"), emoji=d.get("emoji") or "🛒",
            category=d.get("category"), source=d.get("source") or "backup",
        ))
    for c in shop.get("catalog") or []:
        en = (c.get("english") or "").strip()
        if not en:
            continue
        scope = (c.get("scope") or "personal").strip().lower()
        if scope not in ("personal", "global"):
            scope = "personal"
        exists = (
            db.query(models.ShopCatalogItem)
            .filter(
                models.ShopCatalogItem.user_id == owner,
                models.ShopCatalogItem.english == en,
                models.ShopCatalogItem.category == (c.get("category") or "custom"),
            )
            .first()
        )
        if exists:
            continue
        db.add(models.ShopCatalogItem(
            user_id=owner,
            english=en,
            malayalam=c.get("malayalam"),
            emoji=c.get("emoji") or "🛒",
            category=c.get("category") or "custom",
            scope=scope,
            aliases=c.get("aliases"),
        ))
        restored["shop_catalog"] = restored.get("shop_catalog", 0) + 1

    dest_dir = settings.STORAGE_DIR / owner / "shop"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for lst_e in shop.get("lists") or []:
        name = (lst_e.get("name") or "Restored list").strip()
        lst = models.ShopList(
            user_id=owner, name=name,
            description=lst_e.get("description"),
            completed=bool(lst_e.get("completed")),
            total_amount=Decimal(str(lst_e.get("total_amount") or 0)),
            completed_at=_parse_dt(lst_e.get("completed_at")),
            deleted_at=_parse_dt(lst_e.get("deleted_at")),
            blocked_uids=lst_e.get("blocked_uids"),
        )
        db.add(lst)
        db.flush()
        restored["shop_lists"] += 1
        for i in lst_e.get("items") or []:
            db.add(models.ShopItem(
                list_id=lst.id,
                name=i.get("name") or "Item",
                quantity=Decimal(str(i.get("quantity") if i.get("quantity") is not None else 1)),
                unit=i.get("unit"),
                price=Decimal(str(i["price"])) if i.get("price") is not None else None,
                checked=bool(i.get("checked")),
                emoji=i.get("emoji"), category=i.get("category"), notes=i.get("notes"),
                status=i.get("status") or "approved",
                guest_name=i.get("guest_name"),
                added_by=owner,
            ))
            restored["shop_items"] += 1
        for rec in lst_e.get("receipts") or []:
            arc = rec.get("file")
            if not arc:
                continue
            try:
                raw = zf.read(arc)
            except KeyError:
                continue
            row = models.ShopReceipt(
                list_id=lst.id, user_id=owner, image_path="",
                image_mime=rec.get("image_mime"),
                original_name=rec.get("original_name"),
            )
            db.add(row)
            db.flush()
            rel = f"{owner}/shop/{row.id}.enc"
            (settings.STORAGE_DIR / rel).write_bytes(crypto.encrypt_bytes(raw))
            row.image_path = rel
        for sh in lst_e.get("shares") or []:
            token = sh.get("token") or sec.token_urlsafe(16)
            exists = db.query(models.ShopShare).filter(models.ShopShare.token == token).first()
            if exists:
                token = sec.token_urlsafe(16)
            db.add(models.ShopShare(
                list_id=lst.id, token=token, created_by=owner,
                expires_at=_parse_dt(sh.get("expires_at")),
                use_count=int(sh.get("use_count") or 0),
            ))


def _restore_expense_analyser(db: Session, owner: str, ea: dict, restored: dict) -> None:
    for it in ea.get("items") or []:
        mid = it.get("gmail_message_id")
        if mid:
            exists = (
                db.query(models.ExpenseAnalyserItem)
                .filter(
                    models.ExpenseAnalyserItem.user_id == owner,
                    models.ExpenseAnalyserItem.gmail_message_id == mid,
                )
                .first()
            )
            if exists:
                continue
        kwargs = dict(
            user_id=owner,
            gmail_message_id=mid or f"restored-{datetime.utcnow().timestamp()}",
            subject=it.get("subject"), from_addr=it.get("from_addr"),
            received_at=_parse_dt(it.get("received_at")),
            txn_date=it.get("txn_date"), direction=it.get("direction"),
            amount=Decimal(str(it["amount"])) if it.get("amount") is not None else None,
            payee=it.get("payee"), suggested_category=it.get("suggested_category"),
            payment_method=it.get("payment_method"), status=it.get("status") or "pending",
            confidence=it.get("confidence"),
            raw_text_enc=crypto.encrypt_text(it.get("raw_text")),
        )
        db.add(models.ExpenseAnalyserItem(**{k: v for k, v in kwargs.items() if hasattr(models.ExpenseAnalyserItem, k)}))
        restored["ea_items"] += 1


def _restore_ai(db: Session, owner: str, ai: dict, restored: dict) -> None:
    for p in ai.get("providers") or []:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        exists = (
            db.query(models.AiProvider)
            .filter(models.AiProvider.user_id == owner, models.AiProvider.name == name)
            .first()
        )
        if exists:
            continue
        db.add(models.AiProvider(
            user_id=owner, name=name, kind=p.get("kind") or "openai",
            model=p.get("model"), base_url=p.get("base_url"),
            is_default=bool(p.get("is_default")),
            api_key_enc=crypto.encrypt_text(p.get("api_key")),
        ))
    for t in ai.get("threads") or []:
        thread = models.AiChatThread(
            user_id=owner, title=(t.get("title") or "Restored chat")[:200],
        )
        db.add(thread)
        db.flush()
        for m in t.get("messages") or []:
            db.add(models.AiChatMessage(
                thread_id=thread.id,
                role=m.get("role") or "user",
                content_enc=crypto.encrypt_text(m.get("content") or ""),
            ))
        restored["ai_threads"] += 1


@router.get("/export")
def export_backup(
    person_id: Optional[str] = None,
    password: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Zip of the full vault (or one person's health data). Pass ?password= to encrypt."""
    require_owner(current_user)
    if person_id:
        person = (
            db.query(models.Person)
            .filter(models.Person.user_id == vault_id(current_user), models.Person.id == person_id)
            .first()
        )
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
    zip_bytes = build_vault_backup(db, current_user, person_id=person_id)
    if password:
        zip_bytes = crypto.encrypt_backup(zip_bytes, password)
        fname = f"healthvault-backup-{datetime.utcnow().strftime('%Y%m%d')}.hvbak"
        media = "application/octet-stream"
    else:
        fname = f"healthvault-backup-{datetime.utcnow().strftime('%Y%m%d')}.zip"
        media = "application/zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/snapshot")
def snapshot_to_disk(
    password: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Write a full-vault backup into BACKUP_DIR."""
    require_owner(current_user)
    if not settings.BACKUP_DIR:
        raise HTTPException(status_code=400, detail="BACKUP_DIR is not set on the server")
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    blob = build_vault_backup(db, current_user)
    if password:
        blob = crypto.encrypt_backup(blob, password)
        name = f"healthvault-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.hvbak"
    else:
        name = f"healthvault-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.zip"
    dest = settings.BACKUP_DIR / name
    dest.write_bytes(blob)
    return {"ok": True, "path": str(dest), "bytes": len(blob)}


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Restore a previously exported zip (optionally password-encrypted) into this vault."""
    require_owner(current_user)
    blob = await file.read()
    try:
        zip_bytes = crypto.decrypt_backup(blob, password or "") if blob.startswith(b"HV1\0") else blob
        if blob.startswith(b"HV1\0") and not password:
            raise HTTPException(status_code=400, detail="This backup is encrypted — a password is required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decrypt backup — check the password")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Not a valid backup zip")

    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError:
        raise HTTPException(status_code=400, detail="Backup is missing manifest.json")

    owner = vault_id(current_user)
    restored = _restore_modules(db, owner, zf, manifest)
    return {"ok": True, "modules": manifest.get("modules") or [], **restored}


@router.get("/google", response_model=schemas.GoogleDriveStatus)
def google_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.drive_backup import get_or_create, status_dict
    require_owner(current_user)
    return status_dict(get_or_create(db, current_user), db)


@router.post("/google/settings", response_model=schemas.GoogleDriveStatus)
def google_settings(
    body: schemas.GoogleDriveSettingsIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.drive_backup import get_or_create, status_dict
    require_owner(current_user)
    row = get_or_create(db, current_user)
    if body.client_id:
        row.client_id = body.client_id.strip()
    if body.client_secret:
        row.client_secret_enc = crypto.encrypt_text(body.client_secret.strip())
    if body.password:
        row.password_enc = crypto.encrypt_text(body.password)
    if body.enabled is not None:
        if body.enabled and (not row.refresh_token_enc or not (row.password_enc or body.password)):
            raise HTTPException(400, "Connect Google Drive and set a backup password first")
        row.enabled = body.enabled
    if body.hour is not None:
        row.hour = max(0, min(23, int(body.hour)))
    if body.keep_days is not None:
        row.keep_days = max(3, min(90, int(body.keep_days)))
    db.commit()
    db.refresh(row)
    return status_dict(row, db)


@router.post("/google/run")
def google_run_now(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.drive_backup import run_backup
    require_owner(current_user)
    try:
        return run_backup(db, current_user)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/google/disconnect")
def google_disconnect(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.drive_backup import get_or_create, status_dict
    require_owner(current_user)
    row = get_or_create(db, current_user)
    row.refresh_token_enc = None
    row.folder_id = None
    row.connected_email = None
    row.enabled = False
    db.commit()
    return status_dict(row, db)
