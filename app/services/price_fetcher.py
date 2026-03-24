# ============================================
# StealthOak - Price Fetcher Service
# ============================================

import asyncio
from typing import Optional, List, Dict, Any

import httpx

from config import settings


class PriceFetcher:
    """
    Fetches live prices from external APIs.
    
    - Stocks: NSE/BSE via Indian-Stock-Market-API
    - Mutual Funds: mfapi.in
    
    All calls are async for parallel fetching.
    """
    
    def __init__(self):
        """Initialize with configured URLs and timeout."""
        self.stock_api_url = settings.stock_api_base_url
        self.mf_api_url = settings.mf_api_base_url
        self.timeout = settings.api_timeout

        # Disable SSL verification (corporate proxy workaround)
        self.client_kwargs = {
            "timeout": self.timeout,
            "verify": False,  # ← Disables SSL verification
        }
    
    # ----------------------------------------
    # STOCK PRICE FETCHING
    # ----------------------------------------
    
    async def get_stock_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch live price for a single stock.
        
        Args:
            symbol: Stock symbol (e.g., "INFY", "TCS")
        
        Returns:
            Dict with price data or None if failed
            
        Example Response:
            {
                "symbol": "INFY",
                "last_price": 1520.45,
                "change": 15.30,
                "percent_change": 1.02,
                "day_high": 1535.00,
                "day_low": 1502.00
            }
        """
        url = f"{self.stock_api_url}/stock?symbol={symbol}&res=num"
        
        try:
            async with httpx.AsyncClient(**self.client_kwargs) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("status") == "success":
                    stock_data = data.get("data", {})
                    return {
                        "symbol": symbol,
                        "last_price": stock_data.get("last_price"),
                        "change": stock_data.get("change"),
                        "percent_change": stock_data.get("percent_change"),
                        "day_high": stock_data.get("day_high"),
                        "day_low": stock_data.get("day_low"),
                        "previous_close": stock_data.get("previous_close"),
                    }
                else:
                    print(f"⚠️ Stock API error for {symbol}: {data}")
                    return None
                    
        except httpx.TimeoutException:
            print(f"⚠️ Timeout fetching stock price for {symbol}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP error for {symbol}: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"⚠️ Error fetching stock price for {symbol}: {e}")
            return None
    
    async def get_multiple_stock_prices(
        self, 
        symbols: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Fetch prices for multiple stocks in PARALLEL.
        
        Args:
            symbols: List of stock symbols
        
        Returns:
            Dict mapping symbol to price data (or None if failed)
            
        Example:
            symbols = ["INFY", "TCS", "HDFCBANK"]
            result = {
                "INFY": {"last_price": 1520.45, ...},
                "TCS": {"last_price": 3456.75, ...},
                "HDFCBANK": None  # Failed to fetch
            }
        """
        # Create tasks for parallel execution
        tasks = [self.get_stock_price(symbol) for symbol in symbols]
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Map symbols to results
        return dict(zip(symbols, results))
    
    # ----------------------------------------
    # MUTUAL FUND NAV FETCHING
    # ----------------------------------------
    
    async def get_mf_nav(self, scheme_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch latest NAV for a mutual fund.
        
        Args:
            scheme_code: MF scheme code (e.g., "120503")
        
        Returns:
            Dict with NAV data or None if failed
            
        Example Response:
            {
                "scheme_code": "120503",
                "scheme_name": "Axis Bluechip Fund - Direct Growth",
                "nav": 52.1045,
                "date": "21-03-2026"
            }
        """
        url = f"{self.mf_api_url}/mf/{scheme_code}/latest"
        
        try:
            async with httpx.AsyncClient(**self.client_kwargs) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("status") == "SUCCESS":
                    meta: Dict[str, Any] = data.get("meta", {})
                    data_list: List[Dict[str, Any]] = data.get("data", [])
                    
                    if not data_list:
                        return None
                    
                    nav_data: Dict[str, Any] = data_list[0]
                    nav_str = nav_data.get("nav")
                    nav_value: Optional[float] = None
                    
                    if nav_str is not None:
                        try:
                            nav_value = float(nav_str)
                        except (ValueError, TypeError):
                            nav_value = None
                    
                    return {
                        "scheme_code": scheme_code,
                        "scheme_name": meta.get("scheme_name"),
                        "nav": nav_value,
                        "date": nav_data.get("date"),
                    }
                else:
                    print(f"⚠️ MF API error for {scheme_code}: {data}")
                    return None
                    
        except httpx.TimeoutException:
            print(f"⚠️ Timeout fetching MF NAV for {scheme_code}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP error for {scheme_code}: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"⚠️ Error fetching MF NAV for {scheme_code}: {e}")
            return None
    
    async def get_multiple_mf_navs(
        self, 
        scheme_codes: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Fetch NAVs for multiple mutual funds in PARALLEL.
        
        Args:
            scheme_codes: List of scheme codes
        
        Returns:
            Dict mapping scheme_code to NAV data (or None if failed)
        """
        tasks = [self.get_mf_nav(code) for code in scheme_codes]
        results = await asyncio.gather(*tasks)
        return dict(zip(scheme_codes, results))
    
    # ----------------------------------------
    # MUTUAL FUND SEARCH
    # ----------------------------------------
    
    async def search_mutual_funds(
        self, 
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Search for mutual funds by name.
        
        Args:
            query: Search term (e.g., "axis bluechip")
        
        Returns:
            List of matching funds
            
        Example Response:
            [
                {"scheme_code": 120503, "scheme_name": "Axis Bluechip Fund - Direct Growth"},
                {"scheme_code": 120505, "scheme_name": "Axis Bluechip Fund - Regular Growth"},
            ]
        """
        url = f"{self.mf_api_url}/mf/search?q={query}"
        
        try:
            async with httpx.AsyncClient(**self.client_kwargs) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                
                # API returns list directly
                if isinstance(data, list):
                    return [
                        {
                            "scheme_code": item.get("schemeCode"),
                            "scheme_name": item.get("schemeName"),
                        }
                        for item in data[:20]  # Limit to 20 results
                    ]
                else:
                    return []
                    
        except Exception as e:
            print(f"⚠️ Error searching mutual funds: {e}")
            return []


# ----------------------------------------
# SINGLETON INSTANCE
# ----------------------------------------
# Use this throughout the app

price_fetcher = PriceFetcher()
