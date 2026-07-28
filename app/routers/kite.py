"""
Kite Router - Zerodha authentication routes
"""
import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from app.database import get_db
from app.models import Holding, KiteSession, Portfolio, SyncLog
from app.services.kite_service import init_kite_service, get_kite_service
from app.services.price_fetcher import price_fetcher

router = APIRouter(prefix="/kite", tags=["Kite"])

_post_login_redirect_path = "/"


def _is_safe_internal_path(path: str) -> bool:
    return isinstance(path, str) and path.startswith("/") and not path.startswith("//")


async def _get_or_create_default_portfolio(db: AsyncSession) -> Portfolio:
    result = await db.execute(select(Portfolio).where(Portfolio.owner == "Self"))
    portfolio = result.scalar_one_or_none()
    if portfolio:
        return portfolio

    portfolio = Portfolio(name="Main Portfolio", owner="Self")
    db.add(portfolio)
    await db.flush()
    return portfolio


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_code(value: str | None, *, upper: bool = False) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return text.upper() if upper else text


def _map_kite_stock_holding(row: dict) -> dict | None:
    symbol = _normalize_code(str(row.get("tradingsymbol") or row.get("symbol") or ""), upper=True) or ""
    exchange = _normalize_code(str(row.get("exchange") or "NSE"), upper=True) or "NSE"
    quantity = _to_float(row.get("quantity"), 0.0)
    avg_price = _to_float(row.get("average_price"), 0.0)
    name = str(row.get("name") or symbol).strip() or symbol

    if not symbol or quantity <= 0 or avg_price <= 0:
        return None

    instrument_token = row.get("instrument_token")
    try:
        instrument_token = int(instrument_token) if instrument_token is not None else None
    except (TypeError, ValueError):
        instrument_token = None

    return {
        "asset_type": "stock",
        "symbol": symbol,
        "name": name,
        "exchange": exchange,
        "quantity": quantity,
        "avg_price": avg_price,
        "isin": _normalize_code(str(row.get("isin")) if row.get("isin") else None, upper=True),
        "instrument_token": instrument_token,
        "source": "kite_holding",
    }


def _map_kite_mf_holding(row: dict) -> dict | None:
    symbol = str(
        row.get("tradingsymbol")
        or row.get("scheme")
        or row.get("scheme_code")
        or row.get("isin")
        or ""
    ).strip()
    name = str(row.get("fund") or row.get("scheme_name") or row.get("scheme") or symbol).strip()
    quantity = _to_float(row.get("quantity") or row.get("units"), 0.0)
    avg_price = _to_float(row.get("average_price") or row.get("purchase_price") or row.get("nav"), 0.0)
    kite_last_price = _to_float(row.get("last_price") or row.get("nav"), 0.0)
    kite_last_price_date = str(row.get("last_price_date") or "").strip() or None
    isin = _normalize_code(str(row.get("isin") or row.get("tradingsymbol") or ""), upper=True)

    if not symbol or quantity <= 0 or avg_price <= 0:
        return None

    return {
        "asset_type": "mutual_fund",
        "symbol": symbol,
        "name": name or symbol,
        "exchange": None,
        "quantity": quantity,
        "avg_price": avg_price,
        "isin": isin,
        "kite_last_price": kite_last_price if kite_last_price > 0 else None,
        "kite_last_price_date": kite_last_price_date,
        "instrument_token": None,
        "source": "coin_holding",
    }


def _looks_like_mf_scheme_code(value: str | None) -> bool:
    return bool(value and str(value).strip().isdigit())


def _normalize_plan_type(value: str | None) -> str | None:
    lower = (value or "").strip().lower()
    if "direct" in lower:
        return "direct"
    if "regular" in lower:
        return "regular"
    return None


def _normalize_dividend_type(value: str | None) -> str | None:
    lower = (value or "").strip().lower()
    if "growth" in lower:
        return "growth"
    if "idcw" in lower or "dividend" in lower or "payout" in lower:
        return "idcw"
    return None


def _strip_plan_dividend_tokens(name: str) -> str:
    value = (name or "").strip()
    value = re.sub(
        r"\b(direct|regular|plan|growth|idcw|dividend|payout|option)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s*-\s*", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    return value


def _build_mf_name_combinations(fund_name: str, plan_type: str | None, dividend_type: str | None) -> list[str]:
    base_name = _strip_plan_dividend_tokens(fund_name)
    if not base_name:
        return []

    plan_label = "Direct Plan" if plan_type == "direct" else "Regular Plan"
    div_label = "Growth Option" if dividend_type == "growth" else "IDCW Option"

    combos = [
        f"{base_name} - {plan_label} - {div_label}",
        f"{base_name} - {div_label} - {plan_label}",
    ]

    unique: list[str] = []
    for item in combos:
        if item not in unique:
            unique.append(item)
    return unique


def _parse_date_safe(value: str | None) -> dt.date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _is_nav_match(kite_nav: float, mf_nav: float) -> bool:
    tolerance = max(0.05, abs(kite_nav) * 0.001)
    return abs(kite_nav - mf_nav) <= tolerance


def _is_date_match(kite_date: dt.date | None, ref_date: dt.date | None) -> bool:
    if kite_date is None or ref_date is None:
        return True
    # Allow one-day lag for holidays/provider delays.
    return 0 <= (kite_date - ref_date).days <= 1


def _validate_nav_and_date(
    kite_nav: float | None,
    kite_date_raw: str | None,
    ref_nav: float | None,
    ref_date_raw: str | None,
) -> bool:
    kite_date = _parse_date_safe(kite_date_raw)
    ref_date = _parse_date_safe(ref_date_raw)

    nav_ok = True
    if kite_nav is not None and ref_nav is not None:
        nav_ok = _is_nav_match(kite_nav, ref_nav)

    date_ok = _is_date_match(kite_date, ref_date)
    return nav_ok and date_ok


async def _resolve_mf_scheme_code_with_nav_date(
    fund_name: str,
    plan_type: str | None,
    dividend_type: str | None,
    kite_last_price: float | None,
    kite_last_price_date: str | None,
) -> tuple[str | None, str | None, dict]:
    normalized_plan = _normalize_plan_type(plan_type)
    normalized_dividend = _normalize_dividend_type(dividend_type)
    if not normalized_plan or not normalized_dividend:
        return None, None, {"reason": "missing_plan_or_dividend", "queries": [], "candidates": []}

    queries = _build_mf_name_combinations(fund_name, normalized_plan, normalized_dividend)
    if not queries:
        return None, None, {"reason": "empty_queries", "queries": [], "candidates": []}

    target_date = _parse_date_safe(kite_last_price_date)
    candidate_map: dict[str, str] = {}
    debug_candidates: list[dict] = []

    for query in queries:
        search_results = await price_fetcher.search_mutual_funds(query)
        for item in search_results[:20]:
            code = str(item.get("scheme_code") or "").strip()
            scheme_name = str(item.get("scheme_name") or "").strip()
            if code and scheme_name and code not in candidate_map:
                candidate_map[code] = scheme_name

    for code, scheme_name in candidate_map.items():
        nav_result = None
        if target_date:
            nav_result = await price_fetcher.get_mf_nav_on_or_before(code, target_date=target_date, max_lookback_days=2)
        if not nav_result:
            latest = await price_fetcher.get_mf_nav(code)
            if latest and latest.get("nav") is not None:
                nav_result = {
                    "price": float(latest["nav"]),
                    "price_date": str(latest.get("date") or ""),
                }

        if not nav_result:
            debug_candidates.append({
                "scheme_code": code,
                "scheme_name": scheme_name,
                "matched": False,
                "reason": "no_nav",
            })
            continue

        mf_nav = float(nav_result["price"])
        mf_date = _parse_date_safe(nav_result.get("price_date"))
        kite_date = target_date

        nav_ok = bool(kite_last_price is not None and _is_nav_match(kite_last_price, mf_nav))
        date_ok = bool(kite_date is None or (mf_date is not None and 0 <= (kite_date - mf_date).days <= 1))
        matched = nav_ok and date_ok

        debug_candidates.append(
            {
                "scheme_code": code,
                "scheme_name": scheme_name,
                "mf_nav": mf_nav,
                "mf_date": mf_date.isoformat() if mf_date else None,
                "nav_ok": nav_ok,
                "date_ok": date_ok,
                "matched": matched,
            }
        )

        if matched:
            return code, scheme_name, {
                "reason": "matched",
                "queries": queries,
                "candidates": debug_candidates,
            }

    return None, None, {
        "reason": "no_candidate_matched",
        "queries": queries,
        "candidates": debug_candidates,
    }


def _stock_identity_key(symbol: str, exchange: str, isin: str | None, instrument_token: int | None) -> tuple:
    """
    Create a stable identity key for stock holdings.
    
    Key priority (in order of preference):
    1. ISIN (most stable - instrument agnostic)
    2. Symbol + Exchange (fallback when ISIN not available)
    NOTE: instrument_token is NOT used as primary key because existing DB rows
          may not have it stored (created manually or from older syncs without it).
          Using it would create false mismatches and duplicate inserts.
    """
    normalized_symbol = (symbol or "").strip().upper()
    normalized_exchange = (exchange or "NSE").strip().upper()
    normalized_isin = _normalize_code(isin, upper=True)

    # Prefer ISIN if available
    if normalized_isin:
        return ("isin", normalized_isin)
    
    # Fall back to symbol + exchange
    return ("symbol", normalized_symbol, normalized_exchange)


def _mf_identity_key(symbol: str, isin: str | None) -> tuple:
    normalized_symbol = (symbol or "").strip()
    normalized_isin = _normalize_code(isin, upper=True)

    if normalized_isin:
        return ("isin", normalized_isin)
    return ("symbol", normalized_symbol)


def _is_kite_auth_error(error_text: str, error_trace: str) -> bool:
    """Detect token/session/auth failures from KiteConnect exceptions/logs."""
    blob = f"{error_text}\n{error_trace}".lower()
    auth_markers = (
        "tokenexception",
        "accesstoken",
        "access token",
        "invalid session",
        "session expired",
        "session has expired",
        "incorrect `api_key` or `access_token`",
        "incorrect api_key or access_token",
        "invalid token",
        "authorizationexception",
        "not authenticated",
    )
    return any(marker in blob for marker in auth_markers)


async def _get_authenticated_kite(db: AsyncSession):
    """Return an authenticated Kite service from memory or persisted session."""
    kite = get_kite_service()
    if kite and getattr(kite, "access_token", None):
        return kite

    result = await db.execute(
        select(KiteSession)
        .where(KiteSession.is_active.is_(True))
        .order_by(KiteSession.updated_at.desc())
        .limit(1)
    )
    stored_session = result.scalar_one_or_none()

    if not stored_session or not stored_session.access_token:
        raise HTTPException(status_code=401, detail="Kite access token not available. Login again.")

    return init_kite_service(
        api_key=stored_session.api_key,
        api_secret=stored_session.api_secret,
        access_token=stored_session.access_token,
        disable_ssl=settings.kite_disable_ssl,
    )


@router.get("/login")
def kite_login(next: str = "/"):
    """Redirect user to Zerodha login page"""
    global _post_login_redirect_path
    _post_login_redirect_path = next if _is_safe_internal_path(next) else "/"
    
    # Initialize KiteService (singleton)
    kite = init_kite_service(
        api_key=settings.kite_api_key,
        api_secret=settings.kite_api_secret,
        disable_ssl=settings.kite_disable_ssl,
    )
    
    # Get Zerodha login URL
    login_url = kite.get_login_url()
    print(f"[KITE] Redirecting to: {login_url}")
    
    return RedirectResponse(url=login_url)


@router.get("/callback")
async def kite_callback(
    request_token: str = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Zerodha OAuth callback"""
    global _post_login_redirect_path
    
    # Check if login was successful
    if status != "success" or not request_token:
        print(f"[KITE] Login failed: status={status}")
        raise HTTPException(status_code=400, detail="Login failed")
    
    # Get existing KiteService instance
    kite = get_kite_service()
    if not kite:
        raise HTTPException(status_code=500, detail="KiteService not initialized")
    
    try:
        # Exchange request_token for access_token
        session = kite.generate_session(request_token)

        result = await db.execute(select(KiteSession).where(KiteSession.is_active.is_(True)))
        active_sessions = list(result.scalars().all())
        for active_session in active_sessions:
            active_session.is_active = False

        db.add(
            KiteSession(
                api_key=settings.kite_api_key,
                api_secret=settings.kite_api_secret,
                access_token=session.get("access_token"),
                user_id=session.get("user_id"),
                login_time=session.get("login_time"),
                is_active=True,
            )
        )

        holdings = kite.get_holdings()
        
        # Print to terminal for verification
        print("=" * 50)
        print("[KITE] Login successful!")
        print(f"  User ID    : {session.get('user_id')}")
        print(f"  User Name  : {session.get('user_name')}")
        print(f"  Email      : {session.get('email')}")
        print(f"  Access Token: {session.get('access_token')[:20]}...")
        print(f"  Holdings   : {len(holdings)} fetched")
        print("=" * 50)
        
        redirect_path = _post_login_redirect_path if _is_safe_internal_path(_post_login_redirect_path) else "/"
        _post_login_redirect_path = "/"
        return RedirectResponse(url=redirect_path)
        
    except Exception as e:
        print(f"[KITE] Session generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/{asset_kind}")
async def sync_kite_holdings(
    asset_kind: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync holdings from Kite into local holdings table.
    asset_kind: 'stocks' or 'mutualfunds'
    """
    if asset_kind not in {"stocks", "mutualfunds"}:
        raise HTTPException(status_code=404, detail="Unsupported sync target")

    redirect_target = "/stocks/india" if asset_kind == "stocks" else "/mutualfunds/india"
    route_self = f"/kite/sync/{asset_kind}"

    try:
        kite = await _get_authenticated_kite(db)
    except HTTPException as ex:
        if ex.status_code == 401:
            return RedirectResponse(url=f"/kite/login?next={route_self}")
        raise

    sync_log = SyncLog(
        sync_type=f"kite_{asset_kind}",
        status="started",
        started_at=dt.datetime.utcnow(),
    )
    db.add(sync_log)
    await db.flush()

    created = 0
    updated = 0
    skipped = 0
    resolved = 0
    unresolved = 0

    try:
        portfolio = await _get_or_create_default_portfolio(db)

        if asset_kind == "stocks":
            raw_holdings = kite.get_holdings()
            mapped_rows = [m for m in (_map_kite_stock_holding(row) for row in raw_holdings) if m]
            deduped_rows = {}
            for row in mapped_rows:
                key = _stock_identity_key(row["symbol"], row["exchange"], row.get("isin"), row.get("instrument_token"))
                deduped_rows[key] = row
            mapped_rows = list(deduped_rows.values())

            result = await db.execute(select(Holding).where(Holding.asset_type == "stock"))
            existing_rows = list(result.scalars().all())

            existing_map = {}
            for item in existing_rows:
                key = _stock_identity_key(item.symbol, item.exchange or "NSE", item.isin, item.instrument_token)
                existing_map[key] = item

            for row in mapped_rows:
                key = _stock_identity_key(row["symbol"], row["exchange"], row.get("isin"), row.get("instrument_token"))
                existing = existing_map.get(key)

                if not existing:
                    # Create new holding if it doesn't exist
                    holding = Holding(
                        portfolio_id=portfolio.id,
                        symbol=row["symbol"],
                        name=row["name"],
                        asset_type="stock",
                        exchange=row["exchange"],
                        quantity=row["quantity"],
                        avg_price=row["avg_price"],
                        isin=row.get("isin"),
                        instrument_token=row.get("instrument_token"),
                        source=row.get("source", "kite_holding"),
                        last_synced_at=dt.datetime.utcnow(),
                    )
                    db.add(holding)
                    existing_map[key] = holding
                    created += 1
                else:
                    # Update existing holding if necessary
                    unchanged = (
                        round(existing.quantity, 6) == round(row["quantity"], 6)
                        and round(existing.avg_price, 6) == round(row["avg_price"], 6)
                        and (existing.name or "") == (row["name"] or "")
                        and (existing.exchange or "") == (row["exchange"] or "")
                    )

                    if unchanged:
                        skipped += 1
                    else:
                        existing.name = row["name"]
                        existing.exchange = row["exchange"]
                        existing.quantity = row["quantity"]
                        existing.avg_price = row["avg_price"]
                        existing.isin = row.get("isin")
                        existing.instrument_token = row.get("instrument_token")
                        existing.source = row.get("source", existing.source)
                        updated += 1

                    existing.last_synced_at = dt.datetime.utcnow()

        else:
            raw_holdings = kite.get_mf_holdings()
            mapped_rows = [m for m in (_map_kite_mf_holding(row) for row in raw_holdings) if m]
            deduped_rows = {}
            for row in mapped_rows:
                key = _mf_identity_key(row["symbol"], row.get("isin"))
                deduped_rows[key] = row
            mapped_rows = list(deduped_rows.values())
            
            # AMFI fetch is intentionally skipped to avoid sync latency/timeouts on
            # geoblocked or corporate networks. Keep an empty map and use fallback
            # resolver paths below.
            amfi_by_isin = {}

            instrument_rows = kite.get_mf_instruments()
            instruments_by_isin: dict[str, dict] = {
                str(item.get("tradingsymbol") or "").strip(): item
                for item in instrument_rows
                if str(item.get("tradingsymbol") or "").strip()
            }

            result = await db.execute(select(Holding).where(Holding.asset_type == "mutual_fund"))
            existing_rows = list(result.scalars().all())

            # Persisted stabilization map: ISIN -> scheme_code.
            scheme_by_isin: dict[str, str] = {
                _normalize_code(item.isin, upper=True): item.symbol
                for item in existing_rows
                ## Normally symbol is filled with KITE trading symbol, but once we resolve
                ## mutual funds, symbol will be updated to scheme code.
                if _normalize_code(item.isin, upper=True) and _looks_like_mf_scheme_code(item.symbol)
            }

            for row in mapped_rows:
                resolved_code = None
                resolved_name = None
                row["_resolved"] = False

                if _looks_like_mf_scheme_code(row.get("symbol")):
                    resolved_code = row["symbol"]
                    resolved += 1
                else:
                    isin = row.get("isin")
                    if isin and isin in scheme_by_isin:
                        resolved_code = scheme_by_isin[isin]
                        resolved += 1
                    else:
                        instrument = instruments_by_isin.get(isin or "") if isin else None
                        plan_type = _normalize_plan_type(instrument.get("plan") if instrument else None)
                        dividend_type = _normalize_dividend_type(instrument.get("dividend_type") if instrument else None)

                        # User strategy: currently accept only direct+growth holdings.
                        if plan_type and plan_type != "direct":
                            unresolved += 1
                            continue
                        if dividend_type and dividend_type != "growth":
                            unresolved += 1
                            continue

                        if not resolved_code:
                            resolved_code, resolved_name, _debug = await _resolve_mf_scheme_code_with_nav_date(
                                fund_name=row.get("name") or (instrument.get("name") if instrument else "") or "",
                                plan_type=plan_type or "direct",
                                dividend_type=dividend_type or "growth",
                                kite_last_price=row.get("kite_last_price"),
                                kite_last_price_date=row.get("kite_last_price_date"),
                            )

                        if resolved_code:
                            resolved += 1
                        else:
                            unresolved += 1

                if resolved_code:
                    row["symbol"] = resolved_code
                    if resolved_name:
                        row["name"] = resolved_name
                    if row.get("isin"):
                        normalized_isin = _normalize_code(row["isin"], upper=True)
                        if normalized_isin:
                            row["isin"] = normalized_isin
                            scheme_by_isin[normalized_isin] = resolved_code
                    row["_resolved"] = True

            existing_map = {}
            # Secondary map: scheme_code → holding, for resolved holdings that have isin=None
            # (can happen when a holding was resolved via UI before isin was stored)
            resolved_code_map = {}
            for item in existing_rows:
                key = _mf_identity_key(item.symbol, item.isin)
                existing_map[key] = item
                if _looks_like_mf_scheme_code(item.symbol) and not item.isin:
                    resolved_code_map[item.symbol] = item

            for row in mapped_rows:
                # Always save holdings, even unresolved ones (symbol = ISIN as placeholder).
                # Unresolved holdings show an "⚠️ Unresolved" badge and can be fixed via the Resolve UI.
                key = _mf_identity_key(row["symbol"], row.get("isin"))
                existing = existing_map.get(key)

                # Fallback: if no match by ISIN/symbol, check if this row's ISIN maps to
                # a resolved holding that was missing its ISIN (resolved via UI before isin was stored)
                if not existing and row.get("isin") and row["isin"] in scheme_by_isin:
                    fallback_code = scheme_by_isin[row["isin"]]
                    existing = resolved_code_map.get(fallback_code)
                    if existing:
                        # Backfill the missing ISIN on the existing resolved holding
                        existing.isin = row["isin"]

                if not existing:
                    holding = Holding(
                        portfolio_id=portfolio.id,
                        symbol=row["symbol"],
                        name=row["name"],
                        asset_type="mutual_fund",
                        exchange=None,
                        quantity=row["quantity"],
                        avg_price=row["avg_price"],
                        isin=row.get("isin"),
                        instrument_token=None,
                        source=row.get("source", "coin_holding"),
                        last_synced_at=dt.datetime.utcnow(),
                    )
                    db.add(holding)
                    existing_map[key] = holding
                    if row.get("isin"):
                        normalized_isin = _normalize_code(row["isin"], upper=True)
                        if normalized_isin and _looks_like_mf_scheme_code(row["symbol"]):
                            scheme_by_isin[normalized_isin] = row["symbol"]
                    created += 1
                    continue

                # If this holding has already been manually resolved (symbol is numeric),
                # preserve the scheme code and name — only update quantity/avg_price.
                already_resolved = existing.symbol and existing.symbol.strip().isdigit()

                unchanged = (
                    round(existing.quantity, 6) == round(row["quantity"], 6)
                    and round(existing.avg_price, 6) == round(row["avg_price"], 6)
                    and (already_resolved or (existing.name or "") == (row["name"] or ""))
                )

                if unchanged:
                    skipped += 1
                else:
                    if not already_resolved:
                        existing.name = row["name"]
                    existing.quantity = row["quantity"]
                    existing.avg_price = row["avg_price"]
                    existing.isin = row.get("isin")
                    existing.source = row.get("source", existing.source)
                    updated += 1

                existing.last_synced_at = dt.datetime.utcnow()

        sync_log.status = "success"
        sync_log.records_fetched = len(raw_holdings)
        sync_log.records_created = created
        sync_log.records_updated = updated
        sync_log.records_skipped = skipped
        if asset_kind == "mutualfunds":
            sync_log.error_message = f"resolver: resolved={resolved}, unresolved={unresolved}"
        sync_log.completed_at = dt.datetime.utcnow()

        await db.commit()
        return RedirectResponse(
            url=(
                f"{redirect_target}?sync_status=success"
                f"&fetched={len(raw_holdings)}&created={created}&updated={updated}&skipped={skipped}"
                f"&resolved={resolved}&unresolved={unresolved}"
            )
        )
    except Exception as exc:
        import traceback
        error_trace = traceback.format_exc()
        error_msg = f"{str(exc)} | {error_trace}"
        print(f"[SYNC {asset_kind}] ERROR: {error_msg}")

        # If Kite session is invalid/expired, force re-login flow instead of generic failure banner.
        error_text = str(exc)
        if _is_kite_auth_error(error_text, error_trace):
            result = await db.execute(select(KiteSession).where(KiteSession.is_active.is_(True)))
            for session in result.scalars().all():
                session.is_active = False

            sync_log.status = "failed"
            sync_log.error_message = "Kite session expired"
            sync_log.completed_at = dt.datetime.utcnow()
            await db.commit()
            return RedirectResponse(url=f"/kite/login?next={route_self}")

        sync_log.status = "failed"
        sync_log.error_message = str(exc)
        sync_log.completed_at = dt.datetime.utcnow()
        await db.commit()
        return RedirectResponse(url=f"{redirect_target}?sync_status=failed&error=sync_failed")


@router.get("/holdings")
async def kite_holdings(db: AsyncSession = Depends(get_db)):
    """Fetch holdings from Zerodha using the active access token."""
    kite = await _get_authenticated_kite(db)

    try:
        holdings = kite.get_holdings()
        return {
            "count": len(holdings),
            "holdings": holdings,
        }
    except Exception as e:
        print(f"[KITE] Holdings fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

################### DEBUG ROUTES BELOW - NOT FOR PRODUCTION ###################

@router.get("/refresh-amfi-master")
async def refresh_amfi_master():
    """
    Manually refresh the AMFI master data cache.
    Note: AMFI website is geoblocked outside India.
    """
    try:
        print("[AMFI] Starting manual refresh...")
        result = await price_fetcher.get_amfi_isin_scheme_map(force_refresh=True)
        print(f"[AMFI] Refresh complete. Loaded {len(result)} scheme mappings.")
        return {
            "status": "success",
            "message": f"AMFI master data refreshed successfully. Loaded {len(result)} scheme mappings.",
        }
    except Exception as e:
        error_type = type(e).__name__
        print(f"[AMFI] Refresh failed ({error_type}): {str(e)[:200]}")
        
        return {
            "status": "info",
            "message": (
                "AMFI website is unreachable. This is normal if you're outside India (AMFI is geoblocked). "
                "Use the manual '🔍 Resolve' button on each fund to resolve them via mfapi.in instead."
            ),
        }


@router.get("/debug/mf-resolver")
async def debug_mf_resolver(
    fund_name: str = Query(..., description="Base fund name from holdings"),
    plan_type: str = Query(..., description="direct or regular"),
    dividend_type: str = Query(..., description="growth or idcw/payout/dividend"),
    kite_nav: float = Query(..., description="Kite last_price for holding"),
    kite_nav_date: dt.date = Query(..., description="Kite last_price_date (YYYY-MM-DD)"),
):
    """DEBUG: Start resolver from step 3 using assumed plan/dividend and Kite NAV/date."""
    code, name, debug_data = await _resolve_mf_scheme_code_with_nav_date(
        fund_name=fund_name,
        plan_type=plan_type,
        dividend_type=dividend_type,
        kite_last_price=kite_nav,
        kite_last_price_date=kite_nav_date.isoformat(),
    )

    return {
        "input": {
            "fund_name": fund_name,
            "plan_type": plan_type,
            "dividend_type": dividend_type,
            "kite_nav": kite_nav,
            "kite_nav_date": kite_nav_date.isoformat(),
        },
        "resolved_scheme_code": code,
        "resolved_scheme_name": name,
        "debug": debug_data,
    }

@router.get("/debug/mf-holdings")
async def debug_mf_holdings(db: AsyncSession = Depends(get_db)):
    """DEBUG: Fetch raw MF holdings from Kite to inspect all fields."""
    kite = await _get_authenticated_kite(db)

    try:
        mf_holdings = kite.get_mf_holdings()
        return {
            "count": len(mf_holdings),
            "sample": mf_holdings[0] if mf_holdings else None,
            "all": mf_holdings,
        }
    except Exception as e:
        print(f"[KITE] MF Holdings fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
