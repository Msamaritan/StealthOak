# ============================================
# StealthOak - Configuration
# ============================================

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """
    Application settings.
    
    Values can be overridden via environment variables or .env file.
    Example: export STEALTHOAK_DEBUG=true
    """
    
    # --- App Settings ---
    app_name: str = "StealthOak"
    app_version: str = "0.1.0"
    debug: bool = True
    
    # --- Database ---
    # SQLite file stored in project root
    # This file persists your data between runs
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/stealthoak.db"
    
    # --- External APIs ---
    # Stock prices (NSE/BSE)
    stock_api_base_url: str = "https://nse-api-khaki.vercel.app"
    
    # Mutual Fund NAV (mfapi.in)
    mf_api_base_url: str = "https://api.mfapi.in"
    
    # --- Cache Settings (Phase 1+) ---
    # Price cache duration in seconds
    price_cache_ttl: int = 900  # 15 minutes
    
    # --- API Timeout ---
    # Max seconds to wait for external API response
    api_timeout: int = 10
    
    # --- Corporate Proxy (for AMFI/Yahoo Finance behind corporate firewall) ---
    # Set these env vars if behind a corporate proxy:
    # Example: STEALTHOAK_HTTP_PROXY="http://proxy.company.com:8080"
    # httpx will also check http_proxy, https_proxy, no_proxy env vars
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = ""
    
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_disable_ssl: bool = False

    model_config = SettingsConfigDict(
        env_prefix="STEALTHOAK_",  # Env vars: STEALTHOAK_DEBUG, etc.
        env_file=".env",           # Load from .env file if exists
        env_file_encoding="utf-8",
        extra="ignore"             # Ignore unknown env vars
    )


# Single instance to import everywhere
settings = Settings()
