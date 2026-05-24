"""
Insurance Router - metadata-rich insurance tracking (LIC, health, etc.)
"""

import datetime as dt
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import InsurancePolicy, InsurancePremiumPayment


router = APIRouter(prefix="/insurance", tags=["Insurance"])

templates = Jinja2Templates(directory="app/templates")


CATEGORY_LABELS = {
    "lic": "LIC",
    "health": "Health Insurance",
    "general": "General Insurance",
    "other": "Other Insurance",
}

ALLOWED_CATEGORIES = {"lic", "health", "general", "other"}
ALLOWED_FREQUENCIES = {"monthly", "quarterly", "half_yearly", "yearly", "single"}


def _parse_date(value: str, field_name: str, errors: List[str], required: bool = True) -> Optional[dt.date]:
    raw = (value or "").strip()
    if not raw:
        if required:
            errors.append(f"{field_name} is required")
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        errors.append(f"Invalid {field_name}")
        return None


def _parse_float(
    value: str,
    field_name: str,
    errors: List[str],
    required: bool = True,
    positive: bool = False,
) -> Optional[float]:
    raw = (value or "").strip()
    if not raw:
        if required:
            errors.append(f"{field_name} is required")
        return None
    try:
        amount = float(raw)
    except ValueError:
        errors.append(f"Invalid {field_name}")
        return None

    if positive and amount <= 0:
        errors.append(f"{field_name} must be greater than 0")
    return amount


def _parse_policy_form(form, errors: List[str]) -> Dict[str, Optional[object]]:
    policy_name = (form.get("policy_name") or "").strip()
    provider = (form.get("provider") or "").strip()
    policy_category = (form.get("policy_category") or "other").strip().lower()
    policy_type = (form.get("policy_type") or "traditional").strip().lower()
    premium_frequency = (form.get("premium_frequency") or "yearly").strip().lower()

    policy_number = (form.get("policy_number") or "").strip()
    insured_person = (form.get("insured_person") or "").strip()
    nominee = (form.get("nominee") or "").strip() or None
    tax_section = (form.get("tax_section") or "").strip() or None
    notes = (form.get("notes") or "").strip() or None

    if not policy_name:
        errors.append("Policy name is required")
    if not provider:
        errors.append("Provider is required")
    if not policy_number:
        errors.append("Policy number is required")
    if not insured_person:
        errors.append("Insured person is required")

    if policy_category not in ALLOWED_CATEGORIES:
        errors.append("Policy category must be LIC, Health, General, or Other")

    if premium_frequency not in ALLOWED_FREQUENCIES:
        errors.append("Premium frequency is invalid")

    start_date = _parse_date(form.get("start_date", ""), "start date", errors, required=True)
    maturity_date = _parse_date(form.get("maturity_date", ""), "maturity date", errors, required=False)

    premium_amount = _parse_float(
        form.get("premium_amount", ""),
        "premium amount",
        errors,
        required=True,
        positive=True,
    )
    sum_assured = _parse_float(
        form.get("sum_assured", ""),
        "sum assured",
        errors,
        required=False,
        positive=True,
    )
    current_value = _parse_float(
        form.get("current_value", ""),
        "current value",
        errors,
        required=False,
    )

    if start_date and maturity_date and maturity_date < start_date:
        errors.append("Maturity date cannot be earlier than start date")

    is_active_raw = (form.get("is_active") or "true").strip().lower()
    is_active = is_active_raw in {"true", "1", "yes", "on"}

    return {
        "policy_name": policy_name,
        "provider": provider,
        "policy_category": policy_category,
        "policy_type": policy_type,
        "policy_number": policy_number,
        "insured_person": insured_person,
        "nominee": nominee,
        "start_date": start_date,
        "maturity_date": maturity_date,
        "premium_amount": premium_amount,
        "premium_frequency": premium_frequency,
        "sum_assured": sum_assured,
        "current_value": current_value,
        "tax_section": tax_section,
        "notes": notes,
        "is_active": is_active,
    }


@router.get("", response_class=HTMLResponse)
async def insurance_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InsurancePolicy)
        .options(selectinload(InsurancePolicy.premium_payments))
        .order_by(
            InsurancePolicy.policy_category.asc(),
            InsurancePolicy.provider.asc(),
            InsurancePolicy.policy_name.asc(),
        )
    )
    policies: List[InsurancePolicy] = list(result.scalars().all())

    policies_by_category: Dict[str, List[InsurancePolicy]] = {
        "lic": [],
        "health": [],
        "general": [],
        "other": [],
    }
    for policy in policies:
        key = (policy.policy_category or "other").strip().lower()
        if key not in policies_by_category:
            key = "other"
        policies_by_category[key].append(policy)

    total_premium_paid = round(sum(p.total_premium_paid for p in policies), 2)
    active_policy_count = sum(1 for p in policies if p.is_active)

    return templates.TemplateResponse(
        "insurance.html",
        {
            "request": request,
            "policies": policies,
            "policies_by_category": policies_by_category,
            "category_labels": CATEGORY_LABELS,
            "total_policy_count": len(policies),
            "active_policy_count": active_policy_count,
            "total_premium_paid": total_premium_paid,
        },
    )


@router.post("/policy")
async def add_insurance_policy(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    errors: List[str] = []
    payload = _parse_policy_form(form, errors)

    if errors:
        return JSONResponse({"success": False, "errors": errors}, status_code=400)

    policy = InsurancePolicy(**payload)
    db.add(policy)
    await db.flush()

    return JSONResponse({"success": True, "policy_id": policy.id})


@router.get("/policy/{policy_id}")
async def get_policy(policy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {
        "id": policy.id,
        "policy_name": policy.policy_name,
        "provider": policy.provider,
        "policy_category": policy.policy_category,
        "policy_type": policy.policy_type,
        "policy_number": policy.policy_number,
        "insured_person": policy.insured_person,
        "nominee": policy.nominee or "",
        "start_date": policy.start_date.isoformat(),
        "maturity_date": policy.maturity_date.isoformat() if policy.maturity_date else "",
        "premium_amount": policy.premium_amount,
        "premium_frequency": policy.premium_frequency,
        "sum_assured": policy.sum_assured,
        "current_value": policy.current_value,
        "tax_section": policy.tax_section or "",
        "notes": policy.notes or "",
        "is_active": policy.is_active,
    }


@router.put("/policy/{policy_id}")
async def update_policy(
    policy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    form = await request.form()
    errors: List[str] = []
    payload = _parse_policy_form(form, errors)

    if errors:
        return JSONResponse({"success": False, "errors": errors}, status_code=400)

    for key, value in payload.items():
        setattr(policy, key, value)

    await db.flush()
    return JSONResponse({"success": True, "policy_id": policy.id})


@router.delete("/policy/{policy_id}")
async def delete_policy(policy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    await db.delete(policy)
    return {"success": True, "deleted_policy_id": policy_id}


@router.post("/policy/{policy_id}/payment")
async def add_policy_payment(
    policy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    form = await request.form()

    errors: List[str] = []
    payment_date = _parse_date(form.get("payment_date", ""), "payment date", errors, required=True)
    amount = _parse_float(
        form.get("amount", ""),
        "amount",
        errors,
        required=True,
        positive=True,
    )
    tax_claim_amount = _parse_float(
        form.get("tax_claim_amount", ""),
        "tax claim amount",
        errors,
        required=False,
    )

    payment_mode = (form.get("payment_mode") or "").strip() or None
    reference_no = (form.get("reference_no") or "").strip() or None
    notes = (form.get("notes") or "").strip() or None

    if errors:
        return JSONResponse({"success": False, "errors": errors}, status_code=400)

    payment = InsurancePremiumPayment(
        policy_id=policy.id,
        payment_date=payment_date,
        amount=amount,
        payment_mode=payment_mode,
        reference_no=reference_no,
        tax_claim_amount=tax_claim_amount,
        notes=notes,
    )
    db.add(payment)
    await db.flush()

    return JSONResponse({"success": True, "payment_id": payment.id})


@router.get("/policy/{policy_id}/payments")
async def list_policy_payments(policy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InsurancePolicy)
        .options(selectinload(InsurancePolicy.premium_payments))
        .where(InsurancePolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    payments = sorted(policy.premium_payments, key=lambda p: p.payment_date, reverse=True)
    return {
        "policy_id": policy.id,
        "policy_name": policy.policy_name,
        "provider": policy.provider,
        "total_paid": round(policy.total_premium_paid, 2),
        "payments": [
            {
                "id": payment.id,
                "date": payment.payment_date.isoformat(),
                "amount": payment.amount,
                "payment_mode": payment.payment_mode or "",
                "reference_no": payment.reference_no or "",
                "tax_claim_amount": payment.tax_claim_amount,
                "notes": payment.notes or "",
            }
            for payment in payments
        ],
    }
