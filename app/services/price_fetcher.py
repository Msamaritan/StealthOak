# ============================================
# StealthOak - Price Fetcher (Simple)
# ============================================

"""
Uses Yahoo Finance for stocks, mfapi.in for mutual funds.
No complex provider system — just works.
"""

import asyncio
import warnings
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx

from config import settings

# Suppress SSL warnings (corporate proxy)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

class SimpleCache:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, ttl_seconds: int = 900):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: Dict[str, tuple] = {}  # key: (value, timestamp)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value if exists and not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self.ttl:
                return value
            else:
                del self._cache[key]  # Expired
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Store value with current timestamp."""
        self._cache[key] = (value, datetime.now())
    
    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

class PriceFetcher:
    """Fetches live prices for stocks and mutual funds."""

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    
    def __init__(self):
        self.timeout = settings.api_timeout
        self.mf_api_url = settings.mf_api_base_url
        self.client_kwargs = {
            "timeout": self.timeout,
            "verify": False,  # Corporate proxy workaround
        }
        # Common headers to mimic a browser and avoid blocking thinking it is from a script or bot
        # This says the yahoo finance API that we are a chrome browser on windows 10, which is a common user agent string
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Cache: 15 minutes TTL
        self.cache = SimpleCache(ttl_seconds=settings.price_cache_ttl)
    
    async def _request_with_retry(
        self, 
        url: str, 
        headers: Optional[Dict] = None,
        context: str = ""
    ) -> Optional[Dict]:
        """
        Make HTTP request with automatic retry on transient failures.
        
        Args:
            url: The URL to fetch
            headers: Optional headers
            context: Description for logging (e.g., "MF 101762")
        
        Returns:
            JSON response or None if all retries failed
        """
        last_error = None
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(**self.client_kwargs) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    return response.json()
                    
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                last_error = f"HTTP {status_code}"
                
                # Don't retry on client errors (4xx) except 429 (rate limit)
                if 400 <= status_code < 500 and status_code != 429:
                    print(f"⚠️ [{context}] {last_error} - Not retrying")
                    return None
                
                # Retry on server errors (5xx) and rate limiting (429)
                if attempt < self.MAX_RETRIES:
                    wait_time = self.RETRY_DELAY * attempt  # Exponential backoff
                    print(f"⚠️ [{context}] {last_error} - Retry {attempt}/{self.MAX_RETRIES} in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    
            except httpx.TimeoutException:
                last_error = "Timeout"
                if attempt < self.MAX_RETRIES:
                    print(f"⚠️ [{context}] {last_error} - Retry {attempt}/{self.MAX_RETRIES}")
                    await asyncio.sleep(self.RETRY_DELAY)
                    
            except Exception as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES:
                    print(f"⚠️ [{context}] {last_error} - Retry {attempt}/{self.MAX_RETRIES}")
                    await asyncio.sleep(self.RETRY_DELAY)
        
        print(f"❌ [{context}] Failed after {self.MAX_RETRIES} attempts: {last_error}")
        return None

    # ----------------------------------------
    # STOCKS (Yahoo Finance)
    # ----------------------------------------
    
    async def search_stocks(self, query: str) -> List[Dict[str, Any]]:
        """Search for Indian stocks by name or symbol."""
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=15&newsCount=0"
        

        async with httpx.AsyncClient(**self.client_kwargs) as client:
            data = await self._request_with_retry(url, self.headers, f"Stock search: {query}")
    
            if not data:
                return []
            
            results = []
            seen = set()
            
            for quote in data.get("quotes", []):
                symbol = quote.get("symbol", "")
                
                if symbol.endswith(".NS"):
                    stock = {
                        "symbol": symbol.replace(".NS", ""),
                        "name": quote.get("longname") or quote.get("shortname", ""),
                        "exchange": "NSE",
                    }
                elif symbol.endswith(".BO"):
                    stock = {
                        "symbol": symbol.replace(".BO", ""),
                        "name": quote.get("longname") or quote.get("shortname", ""),
                        "exchange": "BSE",
                    }
                else:
                    continue
                
                key = f"{stock['symbol']}_{stock['exchange']}"
                if key not in seen:
                    seen.add(key)
                    results.append(stock)
            
            return results[:10]
    
    async def get_stock_price(self, symbol: str, exchange: str = "NSE") -> Optional[Dict[str, Any]]:
        """Get live price for a stock."""

        cache_key = f"stock_{symbol}_{exchange}"
        cached = self.cache.get(cache_key)
        if cached:
            print(f"🔁 Cache hit for {symbol} ({exchange})")
            return cached

        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        yahoo_symbol = f"{symbol}{suffix}"
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=1d"
        
        data = await self._request_with_retry(url, self.headers, f"Stock: {symbol}")
        
        if not data:
            return None
                
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        
        meta = result[0].get("meta", {})
        current_price = meta.get("regularMarketPrice")
        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        
        if current_price is None:
            return None
        
        change = current_price - previous_close if previous_close else 0
        percent_change = (change / previous_close * 100) if previous_close else 0
        
        price_data = {
            "symbol": symbol,
            "last_price": round(current_price, 2),
            "change": round(change, 2),
            "percent_change": round(percent_change, 2),
            "previous_close": round(previous_close, 2) if previous_close else None,
        }

        self.cache.set(cache_key, price_data)
        print(f"🌐 Fetched: {symbol}")
        return price_data
    
    async def get_multiple_stock_prices(
        self, 
        symbols_with_exchange: List[tuple]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get prices for multiple stocks in parallel."""
        tasks = [self.get_stock_price(s, e) for s, e in symbols_with_exchange]
        results = await asyncio.gather(*tasks)
        return {s: r for (s, _), r in zip(symbols_with_exchange, results)}
    
    # ----------------------------------------
    # MUTUAL FUNDS (mfapi.in)
    # ----------------------------------------
    
    async def search_mutual_funds(self, query: str) -> List[Dict[str, Any]]:
        """Search for mutual funds by name."""
        url = f"{self.mf_api_url}/mf/search?q={query}"
        
        data = await self._request_with_retry(url, None, f"MF search: {query}")
        
        if not data or not isinstance(data, list):
            return []
        
        return [
            {
                "scheme_code": item.get("schemeCode"),
                "scheme_name": item.get("schemeName"),
            }
            for item in data[:20]
        ]
    
    async def get_mf_nav(self, scheme_code: str) -> Optional[Dict[str, Any]]:
        """Get latest NAV for a mutual fund."""
        
        cache_key = f"mf_{scheme_code}"
        cached = self.cache.get(cache_key)
        if cached:
            print(f"🔁 Cache hit for MF {scheme_code}")
            return cached
        
        url = f"{self.mf_api_url}/mf/{scheme_code}/latest"
        
        data = await self._request_with_retry(url, None, f"MF {scheme_code}")
        
        if not data:
            return None
                
        if data.get("status") == "SUCCESS":
            meta = data.get("meta", {})
            data_list = data.get("data", [])
            
            if not data_list:
                return None
            nav_data: Dict[str, Any] = data_list[0]
            nav_str = nav_data.get("nav")
            
            try:
                nav_value = float(nav_str) if nav_str else None
            except (ValueError, TypeError):
                nav_value = None
            
            result = {
                "scheme_code": scheme_code,
                "scheme_name": meta.get("scheme_name"),
                "nav": nav_value,
                "date": nav_data.get("date"),
            }
            # Store in cache
            self.cache.set(cache_key, result)
            print(f"🌐 Fetched: MF {scheme_code}")
            
            return result
        return None
    
    async def get_multiple_mf_navs(
        self, 
        scheme_codes: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get NAVs for multiple mutual funds in parallel."""
        tasks = [self.get_mf_nav(code) for code in scheme_codes]
        results = await asyncio.gather(*tasks)
        return dict(zip(scheme_codes, results))


# Singleton
price_fetcher = PriceFetcher()
