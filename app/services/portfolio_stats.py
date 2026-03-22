# ============================================
# StealthOak - Portfolio Statistics Service
# ============================================

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.models import Holding
from app.services.price_fetcher import price_fetcher


@dataclass
class HoldingWithLivePrice:
    """Holding data enriched with live price."""
    
    # From database
    id: int
    symbol: str
    name: str
    asset_type: str
    exchange: Optional[str]
    quantity: float
    avg_price: float
    invested_value: float
    
    # From live API
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    day_change: Optional[float] = None
    day_change_percent: Optional[float] = None


@dataclass
class PortfolioSummary:
    """Overall portfolio statistics."""
    
    total_invested: float
    total_current_value: float
    total_pnl: float
    total_pnl_percent: float
    day_change: float
    day_change_percent: float
    holdings_count: int
    stocks_count: int
    mf_count: int


class PortfolioStats:
    """
    Calculates portfolio statistics by combining
    database holdings with live prices.
    """
    
    async def enrich_holdings_with_prices(
        self, 
        holdings: List[Holding]
    ) -> List[HoldingWithLivePrice]:
        """
        Fetch live prices and calculate P&L for all holdings.
        
        Args:
            holdings: List of Holding models from database
        
        Returns:
            List of HoldingWithLivePrice with calculated values
        """
        # Separate stocks and mutual funds
        stocks = [h for h in holdings if h.asset_type == "stock"]
        mfs = [h for h in holdings if h.asset_type == "mutual_fund"]
        
        # Fetch prices in parallel
        stock_symbols = [h.symbol for h in stocks]
        mf_codes = [h.symbol for h in mfs]  # symbol stores scheme_code for MF
        
        stock_prices = await price_fetcher.get_multiple_stock_prices(stock_symbols)
        mf_prices = await price_fetcher.get_multiple_mf_navs(mf_codes)
        
        # Enrich holdings
        enriched = []
        
        for holding in holdings:
            # Get live price based on asset type
            if holding.asset_type == "stock":
                price_data = stock_prices.get(holding.symbol)
                current_price = price_data.get("last_price") if price_data else None
                day_change = price_data.get("change") if price_data else None
                day_change_pct = price_data.get("percent_change") if price_data else None
            else:
                price_data = mf_prices.get(holding.symbol)
                current_price = price_data.get("nav") if price_data else None
                day_change = None  # NAV doesn't have intraday change
                day_change_pct = None
            
            # Calculate values
            invested_value = holding.quantity * holding.avg_price
            current_value = None
            pnl = None
            pnl_percent = None
            
            if current_price is not None:
                current_value = holding.quantity * current_price
                pnl = current_value - invested_value
                pnl_percent = (pnl / invested_value) * 100 if invested_value > 0 else 0
            
            enriched.append(HoldingWithLivePrice(
                id=holding.id,
                symbol=holding.symbol,
                name=holding.name,
                asset_type=holding.asset_type,
                exchange=holding.exchange,
                quantity=holding.quantity,
                avg_price=holding.avg_price,
                invested_value=invested_value,
                current_price=current_price,
                current_value=current_value,
                pnl=pnl,
                pnl_percent=pnl_percent,
                day_change=day_change,
                day_change_percent=day_change_pct,
            ))
        
        return enriched
    
    def calculate_summary(
        self, 
        enriched_holdings: List[HoldingWithLivePrice]
    ) -> PortfolioSummary:
        """
        Calculate overall portfolio summary.
        
        Args:
            enriched_holdings: Holdings with live prices
        
        Returns:
            PortfolioSummary with totals
        """
        total_invested = 0.0
        total_current = 0.0
        total_day_change = 0.0
        stocks_count = 0
        mf_count = 0
        
        for h in enriched_holdings:
            total_invested += h.invested_value
            
            if h.current_value is not None:
                total_current += h.current_value
            else:
                # If price unavailable, use invested as current
                total_current += h.invested_value
            
            if h.day_change is not None:
                total_day_change += h.day_change * h.quantity
            
            if h.asset_type == "stock":
                stocks_count += 1
            else:
                mf_count += 1
        
        total_pnl = total_current - total_invested
        total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        day_change_percent = (total_day_change / total_current * 100) if total_current > 0 else 0
        
        return PortfolioSummary(
            total_invested=round(total_invested, 2),
            total_current_value=round(total_current, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_percent=round(total_pnl_percent, 2),
            day_change=round(total_day_change, 2),
            day_change_percent=round(day_change_percent, 2),
            holdings_count=len(enriched_holdings),
            stocks_count=stocks_count,
            mf_count=mf_count,
        )
    
    def calculate_asset_allocation(
        self, 
        enriched_holdings: List[HoldingWithLivePrice]
    ) -> Dict[str, float]:
        """
        Calculate percentage allocation by asset type.
        
        Returns:
            {"stock": 45.5, "mutual_fund": 54.5}
        """
        total_value = sum(
            h.current_value or h.invested_value 
            for h in enriched_holdings
        )
        
        if total_value == 0:
            return {"stock": 0, "mutual_fund": 0}
        
        stock_value = sum(
            h.current_value or h.invested_value 
            for h in enriched_holdings 
            if h.asset_type == "stock"
        )
        
        mf_value = total_value - stock_value
        
        return {
            "stock": round((stock_value / total_value) * 100, 2),
            "mutual_fund": round((mf_value / total_value) * 100, 2),
        }
    
    def get_top_holdings(
        self, 
        enriched_holdings: List[HoldingWithLivePrice],
        limit: int = 5
    ) -> List[HoldingWithLivePrice]:
        """
        Get top holdings by current value.
        
        Args:
            enriched_holdings: All holdings
            limit: Number of top holdings to return
        
        Returns:
            Top N holdings sorted by value
        """
        sorted_holdings = sorted(
            enriched_holdings,
            key=lambda h: h.current_value or h.invested_value,
            reverse=True
        )
        return sorted_holdings[:limit]


# ----------------------------------------
# SINGLETON INSTANCE
# ----------------------------------------

portfolio_stats = PortfolioStats()
