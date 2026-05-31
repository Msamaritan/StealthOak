"""
Centralized formatting utilities for dates and amounts.

These functions ensure consistent formatting across the entire application.
"""

from datetime import date
from typing import Optional, Union


CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
}


def format_date_dd_mm_yyyy(value: Optional[Union[date, str]]) -> str:
    """
    Format date to DD/MM/YYYY format.
    
    Args:
        value: date object or ISO format string (YYYY-MM-DD)
    
    Returns:
        Formatted date string in DD/MM/YYYY format, or empty string if None
    """
    if value is None:
        return ""
    
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except (ValueError, TypeError):
            return ""
    
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    
    return ""


def format_indian_rupee(value: Optional[Union[float, int, str]]) -> str:
    """
    Format amount to Indian rupee display format (x,xx,xx,xxx).
    
    Examples:
        100 -> "100.00"
        1000 -> "1,000.00"
        100000 -> "1,00,000.00"
        1000000 -> "10,00,000.00" (10 lakhs)
        10000000 -> "1,00,00,000.00" (1 crore)
    
    Args:
        value: Numeric value to format, can be float, int, or string
    
    Returns:
        Formatted string with Indian rupee convention, or "0.00" if invalid
    """
    if value is None or value == "":
        return "0.00"
    
    # Remove common currency formatting characters before numeric parsing.
    value_str = str(value).replace("₹", "").replace(",", "").strip()
    
    try:
        num = float(value_str)
    except (ValueError, TypeError):
        return "0.00"
    
    # Format to 2 decimal places
    formatted = f"{abs(num):.2f}"
    parts = formatted.split(".")
    int_part = parts[0]
    dec_part = parts[1]
    
    # Apply Indian numbering format (x,xx,xx,xxx)
    if len(int_part) <= 3:
        return int_part + "." + dec_part
    
    # Split into groups of 2 from right, with last group of 3
    last_three = int_part[-3:]
    remaining = int_part[:-3]
    
    # Add commas between groups of 2
    result = ""
    for i, digit in enumerate(reversed(remaining)):
        if i > 0 and i % 2 == 0:
            result = "," + result
        result = digit + result
    
    return result + "," + last_three + "." + dec_part


def format_currency(
    value: Optional[Union[float, int, str]],
    currency: str = "INR",
    decimals: int = 2,
) -> str:
    """Format a numeric value as currency, defaulting to INR formatting."""
    currency_code = (currency or "INR").upper()
    symbol = CURRENCY_SYMBOLS.get(currency_code, f"{currency_code} ")
    safe_decimals = max(0, int(decimals))

    if value is None or value == "":
        if safe_decimals == 0:
            return f"{symbol}0"
        return f"{symbol}0.{('0' * safe_decimals)}"

    value_str = (
        str(value)
        .replace("₹", "")
        .replace("$", "")
        .replace("€", "")
        .replace(",", "")
        .strip()
    )

    try:
        num = float(value_str)
    except (ValueError, TypeError):
        if safe_decimals == 0:
            return f"{symbol}0"
        return f"{symbol}0.{('0' * safe_decimals)}"

    sign = "-" if num < 0 else ""

    if currency_code == "INR":
        formatted = f"{abs(num):.{safe_decimals}f}"
        if safe_decimals > 0:
            int_part, dec_part = formatted.split(".")
        else:
            int_part, dec_part = formatted, ""

        if len(int_part) > 3:
            last_three = int_part[-3:]
            remaining = int_part[:-3]
            grouped = ""
            for i, digit in enumerate(reversed(remaining)):
                if i > 0 and i % 2 == 0:
                    grouped = "," + grouped
                grouped = digit + grouped
            int_part = grouped + "," + last_three

        amount = f"{int_part}.{dec_part}" if safe_decimals > 0 else int_part
        return f"{sign}{symbol}{amount}"

    amount = f"{abs(num):,.{safe_decimals}f}" if safe_decimals > 0 else f"{abs(num):,.0f}"
    return f"{sign}{symbol}{amount}"
