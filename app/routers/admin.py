# ============================================
# StealthOak - Admin Router
# ============================================

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user, hash_password
from app.utils import get_configured_templates

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = get_configured_templates()


def _check_admin(user: User):
    """Verify user is admin, raise 403 if not"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/users", response_class=HTMLResponse)
async def admin_users_list(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin panel: List all users"""
    _check_admin(current_user)
    
    result = await db.execute(
        select(User)
        .order_by(User.id.asc())
    )
    all_users: List[User] = list(result.scalars().all())
    
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": all_users,
            "total_users": len(all_users),
        }
    )


@router.post("/user/{user_id}/toggle-admin")
async def toggle_user_admin(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin action: Toggle admin status for a user"""
    _check_admin(current_user)
    
    # Prevent admin from removing their own admin status
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_admin = not user.is_admin
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/user/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin action: Toggle active status for a user"""
    _check_admin(current_user)
    
    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = not user.is_active
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/user")
async def create_user(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin action: Create a new user"""
    _check_admin(current_user)
    
    form = await request.form()
    username = (form.get("username") or "").strip().lower()
    display_name = (form.get("display_name") or "").strip()
    password = form.get("password") or ""
    
    errors = []
    
    # Validate username
    if not username:
        errors.append("Username is required")
    elif len(username) < 3:
        errors.append("Username must be at least 3 characters")
    elif " " in username:
        errors.append("Username cannot contain spaces")
    else:
        # Check if username already exists
        result = await db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none():
            errors.append(f"Username '{username}' already exists")
    
    # Validate display name
    if not display_name:
        errors.append("Display name is required")
    
    # Validate password
    if not password:
        errors.append("Password is required")
    elif len(password) < 4:
        errors.append("Password must be at least 4 characters")
    elif len(password.encode('utf-8')) > 72:
        errors.append("Password is too long (max 72 bytes)")
    
    if errors:
        return JSONResponse(
            {"success": False, "errors": errors},
            status_code=400
        )
    
    # Create new user
    new_user = User(
        username=username,
        display_name=display_name,
        hashed_password=hash_password(password),
        is_active=True,
        is_admin=False,  # New users are regular users by default
    )
    
    db.add(new_user)
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)
