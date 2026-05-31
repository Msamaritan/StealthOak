"""
KiteConnect integration service for Zerodha API
"""
import csv
import io
import logging
import urllib3
import warnings
from datetime import datetime
from typing import Optional, Dict, List, Any

import httpx
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

# Suppress SSL warnings (corporate proxy)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class KiteService:
    """Service for interacting with Zerodha KiteConnect API"""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: Optional[str] = None,
        disable_ssl: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.kite = KiteConnect(api_key=api_key, disable_ssl=disable_ssl)

        if disable_ssl:
            logger.warning("KiteConnect SSL verification is disabled")
        
        if access_token:
            self.kite.set_access_token(access_token)
    
    # ==================== Authentication ====================
    
    def get_login_url(self) -> str:
        """Get Zerodha login URL for OAuth"""
        return self.kite.login_url()
    
    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """
        Exchange request_token for access_token after user login
        
        Args:
            request_token: Token received from Zerodha callback
            
        Returns:
            Session data including access_token
        """
        try:
            session = self.kite.generate_session(
                request_token=request_token,
                api_secret=self.api_secret
            )
            self.set_access_token(session["access_token"])
            logger.info(f"Session generated for user: {session.get('user_id')}")
            return session
        except Exception as e:
            logger.error(f"Failed to generate session: {e}")
            raise
    
    def set_access_token(self, access_token: str) -> None:
        """Set access token for authenticated requests"""
        self.access_token = access_token
        self.kite.set_access_token(access_token)
    
    def is_authenticated(self) -> bool:
        """Check if current session is valid"""
        try:
            profile = self.kite.profile()
            return profile is not None
        except Exception:
            return False
    
    # ============ All safety critical operations are blocked =================
    
    def place_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.place_order is blocked')
    
    def modify_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.modify_order is blocked')
    
    def cancel_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.cancel_order is blocked')
    
    def exit_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.exit_order is blocked')
    
    def place_mf_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.place_mf_order is blocked')
    
    def cancel_mf_order(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.cancel_mf_order is blocked')
    
    def place_gtt(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.place_gtt is blocked')
    
    def cancel_gtt(self, *args, **kwargs) -> Dict[str, Any]:
        raise PermissionError('kite.cancel_gtt is blocked')
    
    # ==================== Portfolio Data ====================
    
    def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Fetch current holdings from Zerodha
        
        Returns:
            List of holdings with structure:
            {
                'tradingsymbol': 'INFY',
                'exchange': 'NSE',
                'isin': 'INE009A01021',
                'quantity': 100,
                'average_price': 1500.0,
                'last_price': 1550.0,
                'pnl': 5000.0,
                'instrument_token': 408065,
                ...
            }
        """
        try:
            holdings = self.kite.holdings()
            logger.info(f"Fetched {len(holdings)} holdings")
            return holdings
        except Exception as e:
            logger.error(f"Failed to fetch holdings: {e}")
            raise
    
    def get_positions(self) -> Dict[str, List[Dict]]:
        """
        Fetch day and net positions
        
        Returns:
            {'day': [...], 'net': [...]}
        """
        try:
            positions = self.kite.positions()
            logger.info(f"Fetched positions: {len(positions.get('net', []))} net, {len(positions.get('day', []))} day")
            return positions
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            raise
    
    # ==================== Orders & Trades ====================
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch all orders for the day
        
        Returns:
            List of orders with execution details
        """
        try:
            orders = self.kite.orders()
            logger.info(f"Fetched {len(orders)} orders")
            return orders
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            raise
    
    def get_trades(self) -> List[Dict[str, Any]]:
        """
        Fetch all executed trades for the day
        
        Returns:
            List of trades with structure:
            {
                'trade_id': '123456',
                'order_id': '789012',
                'tradingsymbol': 'INFY',
                'exchange': 'NSE',
                'transaction_type': 'BUY',
                'quantity': 10,
                'average_price': 1500.0,
                'fill_timestamp': '2024-01-15 10:30:00',
                ...
            }
        """
        try:
            trades = self.kite.trades()
            logger.info(f"Fetched {len(trades)} trades")
            return trades
        except Exception as e:
            logger.error(f"Failed to fetch trades: {e}")
            raise
    
    # ==================== Instruments & Quotes ====================
    
    def get_quote(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get live quotes for symbols
        
        Args:
            symbols: List like ['NSE:INFY', 'BSE:TCS']
            
        Returns:
            Quote data with LTP, OHLC, etc.
        """
        try:
            quotes = self.kite.quote(symbols)
            return quotes
        except Exception as e:
            logger.error(f"Failed to fetch quotes: {e}")
            raise
    
    def get_ltp(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get last traded price for symbols (lightweight)
        
        Args:
            symbols: List like ['NSE:INFY', 'BSE:TCS']
        """
        try:
            return self.kite.ltp(symbols)
        except Exception as e:
            logger.error(f"Failed to fetch LTP: {e}")
            raise
    
    # ==================== MF Holdings ====================
    
    def get_mf_holdings(self) -> List[Dict[str, Any]]:
        """
        Fetch mutual fund holdings (if using Zerodha Coin)
        
        Returns:
            List of MF holdings
        """
        try:
            mf_holdings = self.kite.mf_holdings()
            logger.info(f"Fetched {len(mf_holdings)} MF holdings")
            return mf_holdings
        except Exception as e:
            logger.error(f"Failed to fetch MF holdings: {e}")
            raise

    def get_mf_instruments(self) -> List[Dict[str, Any]]:
        """
        Fetch MF instruments master list from Kite (/mf/instruments).

        Returns:
            List of instrument rows with keys like tradingsymbol, name, plan, dividend_type.
        """
        if not self.access_token:
            raise ValueError("Access token not set")

        url = "https://api.kite.trade/mf/instruments"
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }

        try:
            with httpx.Client(timeout=30.0, verify=False) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()

            csv_text = response.text
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = [dict(row) for row in reader if row.get("tradingsymbol")]
            logger.info(f"Fetched {len(rows)} MF instruments")
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch MF instruments: {e}")
            raise


# Singleton pattern for app-wide use
_kite_service: Optional[KiteService] = None


def get_kite_service() -> Optional[KiteService]:
    """Get the global KiteService instance"""
    return _kite_service


def init_kite_service(
    api_key: str,
    api_secret: str,
    access_token: Optional[str] = None,
    disable_ssl: bool = False,
) -> KiteService:
    """Initialize the global KiteService"""
    global _kite_service
    _kite_service = KiteService(api_key, api_secret, access_token, disable_ssl)
    return _kite_service