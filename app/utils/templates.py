"""
Jinja2 template configuration utilities.
"""

from fastapi.templating import Jinja2Templates
from app.utils.formatting import (
    format_currency,
    format_date_dd_mm_yyyy,
    format_indian_rupee,
)


def get_configured_templates(template_dir: str = "app/templates") -> Jinja2Templates:
    """
    Create a Jinja2Templates instance with centralized filters pre-configured.
    
    Use this instead of creating Jinja2Templates directly in routers.
    
    Args:
        template_dir: Directory containing templates
    
    Returns:
        Configured Jinja2Templates instance with custom filters registered
    """
    templates = Jinja2Templates(directory=template_dir)
    templates.env.filters["format_date_dd_mm_yyyy"] = format_date_dd_mm_yyyy
    templates.env.filters["format_indian_rupee"] = format_indian_rupee
    templates.env.filters["format_currency"] = format_currency
    return templates
