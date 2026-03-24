# StealthOak

> A privacy-first portfolio tracker for passive investors.
> 
> *"Silent. Patient. Compounds over decades."*

---

## Table of Contents

- [About](#about)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Setup](#setup)
- [Project Structure](#project-structure)
- [Architecture Deep Dive](#architecture-deep-dive)
  - [config.py](#configpy)
  - [app/database.py](#appdatabasepy)
- [API Reference](#api-reference)
- [Development Notes](#development-notes)

---

## About

StealthOak is a **personal portfolio management website** built for Indian investors who:
- Value **privacy** (no broker API access, no third-party tracking)
- Follow **passive investing** (not checking prices 5x/day)
- Want **all investments in one place** (Stocks + Mutual Funds)
- Need **data persistence** (come back after weeks, data is intact)

### Why "StealthOak"?
- **Stealth**: Private, not constantly monitoring
- **Oak**: Grows slow, silent, but massive over decades (compounding!)

---

## Features

### Phase 0 (Current)
- [ ] Add/View/Delete Stocks
- [ ] Add/View/Delete Mutual Funds (with search)
- [ ] Dashboard with combined view
- [ ] Live price fetching (parallel API calls)
- [ ] Data persistence (SQLite)

### Phase 1 (Planned)
- [ ] Multi-portfolio (Self + Mom)
- [ ] CSV import from Zerodha
- [ ] MF overlap analysis (stock-level)
- [ ] Price caching with manual refresh

### Phase 2+ (Future)
- [ ] SIP auto-tracking
- [ ] Rolling returns graphs
- [ ] XIRR/CAGR calculations

---

## Tech Stack

| Layer | Technology | Why |
|-------|------------|-----|
| Backend | FastAPI | Async-first, auto-docs, modern Python |
| Templating | Jinja2 | Simple HTML, no JS frameworks |
| Database | SQLite + SQLAlchemy | Zero config, file-based, persists locally |
| HTTP Client | httpx | Async API calls for parallel price fetching |
| Validation | Pydantic | Auto request/response validation |

---

## Setup

### Prerequisites
- Python 3.11+
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/Msamaritan/StealthOak.git
cd StealthOak

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the App

```bash
# Start the server
uvicorn run:app --reload

# Open in browser
# http://127.0.0.1:8000
```

### Stopping the App
Press `Ctrl+C` in terminal. Your data is safely stored in `stealthoak.db`.

---

## Project Structure

```
StealthOak/
├── run.py                  # Entry point
├── config.py               # All settings in one place
├── requirements.txt        # Python dependencies
├── README.md               # You are here!
├── .gitignore              # Files to ignore in git
├── stealthoak.db           # SQLite database (auto-created, git-ignored)
|
├── app/
    ├── __init__.py         # App package init
    ├── database.py         # Database engine, sessions, base model
    |
    ├── models/             # SQLAlchemy models (tables)
    |   ├── __init__.py
    |   ├── portfolio.py
    |   ├── holding.py
    |   ├── transaction.py
    |
    ├── schemas/            # Pydantic schemas (validation)
    |   ├── __init__.py
    |   ├── portfolio.py
    |   ├── holding.py
    |
    ├── routers/            # API endpoints
    |   ├── __init__.py
    |   ├── dashboard.py
    |   ├── stocks.py
    |   ├── mutualfunds.py
    |
    ├── services/           # Business logic
    |   ├── __init__.py
    |   ├── price_fetcher.py
    |   ├── portfolio_stats.py
    |
    ├── templates/          # Jinja2 HTML templates
    |   ├── base.html
    |   ├── dashboard.html
    |   ├── ...
    |
    ├── static/             # CSS, JS files
        ├── css/
        ├── js/
```

---

## Architecture Deep Dive

### `config.py`

#### What?
Centralized place for all application settings â€” database paths, API URLs, timeouts, feature flags.

#### Why?
| Problem | Solution |
|---------|----------|
| Hardcoded values scattered everywhere | Single source of truth |
| Can't change settings without editing code | Override via environment variables |
| Secrets committed to git | Load from `.env` file (git-ignored) |

#### How?

```python
from config import settings

# Use anywhere in the app
print(settings.database_url)
print(settings.mf_api_base_url)
print(settings.api_timeout)
```

**Key Settings:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `database_url` | `sqlite:///stealthoak.db` | Where data is stored |
| `stock_api_base_url` | `https://nse-api-khaki.vercel.app` | NSE/BSE price API |
| `mf_api_base_url` | `https://api.mfapi.in` | Mutual fund NAV API |
| `price_cache_ttl` | 900 (15 min) | Cache duration (Phase 1+) |
| `api_timeout` | 10 seconds | Max wait for external APIs |

**Override via environment:**
```bash
export STEALTHOAK_DEBUG=false
export STEALTHOAK_API_TIMEOUT=30
```

---

### `app/database.py`

#### What?
Foundation layer connecting the application to SQLite. Sets up:
- Database engine (connection manager)
- Session factory (creates database sessions)
- Base class (all models inherit from this)
- Dependency injection (FastAPI gets database sessions)

#### Why?
| Without database.py | With database.py |
|---------------------|------------------|
| Connection logic scattered | Centralized management |
| Manual open/close | Auto-managed sessions |
| Sync blocks FastAPI | Async, non-blocking |

#### How?

**Concept 1: Engine**
Engine manages the connection pool to the database.

**Concept 2: Session**
A workspace for database operations:
```
1. Open session
2. Query/Add/Update data
3. Commit (save) or Rollback (undo)
4. Close session
```

**Concept 3: Dependency Injection**
FastAPI automatically provides sessions to routes:
```python
@app.get("/stocks")
async def get_stocks(db: AsyncSession = Depends(get_db)):
    # db is automatically provided, committed, and closed!
    result = await db.execute(select(Holding))
    return result.scalars().all()
```

**Concept 4: Base Model**
All database tables inherit from `Base`:
```python
class Holding(Base):
    __tablename__ = "holdings"
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
```

**Lifecycle:**
```
App Startup  --> init_db()    --> Creates tables
Request      --> get_db()     --> Provides session â†’ Auto commit/rollback
App Shutdown --> close_db()   --> Closes connections
```

### `app/models/`

#### What?
Python classes that represent database tables. One class = one table.

#### Why?
| Concept | Benefit |
|---------|---------|
| ORM (Object-Relational Mapping) | Work with Python objects, not raw SQL |
| Relationships | Navigate between tables easily (`portfolio.holdings`) |
| Validation | Type hints catch errors early |
| Migrations | Schema changes are trackable (Alembic) |

#### Models Overview

**Portfolio**
```
|-----------------------------------------|
| portfolios                              |
|-----------------------------------------|
| Column       | Type    | Description    |
|--------------|---------|----------------|
| id           | INTEGER | Primary key    |
| name         | VARCHAR | Portfolio name |
| owner        | VARCHAR | "Self", "Mom"  |
| created_at   | DATETIME| Creation time  |
|-----------------------------------------|
```

**Holding**
```
|-------------------------------------------------|
| holdings                                        |
|-------------------------------------------------|
| Column       | Type    | Description            |
|--------------|---------|------------------------|
| id           | INTEGER | Primary key            |
| portfolio_id | INTEGER | FK â†’ portfolios.id     |
| symbol       | VARCHAR | "INFY" or "120503"     |
| name         | VARCHAR | Full name              |
| asset_type   | VARCHAR | "stock" / "mutual_fund"|
| exchange     | VARCHAR | "NSE" / "BSE" / NULL   |
| quantity     | FLOAT   | Shares or units        |
| avg_price    | FLOAT   | Average buy price      |
| created_at   | DATETIME| Creation time          |
| updated_at   | DATETIME| Last update time       |
|-------------------------------------------------|
```

**Transaction** (Phase 2+)
```
|-------------------------------------------------|
| transactions                                    |
|-------------------------------------------------|
| Column       | Type    | Description            |
|--------------|---------|------------------------|
| id           | INTEGER | Primary key            |
| holding_id   | INTEGER | FK â†’ holdings.id       |
| type         | VARCHAR | "BUY" / "SELL"         |
| date         | DATE    | Transaction date       |
| quantity     | FLOAT   | Shares/units traded    |
| price        | FLOAT   | Price at transaction   |
| notes        | VARCHAR | Optional notes         |
| created_at   | DATETIME| Record creation time   |
|-------------------------------------------------|
```

#### Relationships
```
Portfolio (1) ------< (N) Holding (1) ------< (N) Transaction
```
- One portfolio has many holdings
- One holding has many transactions
- Delete portfolio â†’ cascades to holdings â†’ cascades to transactions

#### Key Concepts Explained

**Foreign Key (FK)**
A link between tables. `holdings.portfolio_id` must match an existing `portfolios.id`:
```
portfolios table          holdings table
|--------------|         |---------------------------|
| id | name    |         | id | portfolio_id | symbol|
|----|---------|         |----|--------------|-------|
| 1  | Main    |<-----------| 1  | 1            | INFY  |
|    |         |<-----------| 2  | 1            | TCS   |
| 2  | Mom's   |<-----------| 3  | 2            | HDFC  |
|--------------|         |---------------------------|
```

**Cascade Delete**
When you delete a portfolio, all its holdings are automatically deleted:
```python
# ondelete="CASCADE" in ForeignKey
# cascade="all, delete-orphan" in relationship
```

**Mapped[] Type Hints**
SQLAlchemy 2.0 style for defining columns:
```python
# Required field (can't be NULL)
name: Mapped[str] = mapped_column(String(100), nullable=False)

# Optional field (can be NULL)
exchange: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
```

**@property for Computed Values**
Not stored in database, calculated on-the-fly:
```python
@property
def invested_value(self) -> float:
    return self.quantity * self.avg_price

# Usage
holding.invested_value  # Returns 70000 (if qty=50, price=1400)
```

### `app/schemas/`

#### What?
Pydantic classes that define the shape of data moving **in and out** of the API. They handle validation, transformation, and documentation.

#### Why?
| Models (SQLAlchemy) | Schemas (Pydantic) |
|---------------------|-------------------|
| Define database tables | Define API contracts |
| All columns including internal ones | Only expose what client needs |
| Used for database operations | Used for request/response |
| `id`, `created_at` auto-generated | Not needed in "Create" schema |

#### Schema Types

| Type | Purpose | Example |
|------|---------|---------|
| `*Create` | Validate incoming data for new records | `HoldingCreate` |
| `*Update` | Partial updates (all fields optional) | `HoldingUpdate` |
| `*Response` | Format data going back to client | `HoldingResponse` |
| `*WithPrice` | Response with live price data | `HoldingWithPrice` |

#### Data Flow
Request JSON → Schema (validate) → Model (save) → Schema (format) → Response JSON

#### Key Concepts

**Field Validation**
```python
name: str = Field(
    ...,              # Required
    min_length=1,     # Can't be empty
    max_length=100,   # Limit length
)

quantity: float = Field(..., gt=0)  # Must be > 0

```
#### Auto Transformation
```python
@field_validator("symbol")
@classmethod
def symbol_uppercase(cls, v: str) -> str:
    return v.upper().strip()

# Input: "  infy  " → Output: "INFY"
```
### Schema Overview
#### Portfolio Schema
| Schema | Fields | Used For|
| ------ | ------ | ------- |
| PortfolioCreate | name, owner	| POST /api/portfolios
| PortfolioUpdate |	name?, owner? | PATCH /api/portfolios/{id}
| PortfolioResponse | id, name, owner, created_at | GET responses

#### Portfolio Schema
| Schema | Fields | Used For|
| ------ | ------ | ------- |
HoldingCreate |	symbol, name, asset_type, exchange?, quantity, avg_price |	POST /api/stocks
HoldingUpdate |	name?, quantity?, avg_price?, exchange? | PATCH /api/stocks/{id}
HoldingResponse | id, symbol, name, asset_type, exchange, quantity, avg_price, invested_value |	GET responses
HoldingWithPrice |	...HoldingResponse + current_price, pnl, pnl_percent, day_change |	Dashboard
MFSearchResult |	scheme_code, scheme_name |	MF search results

--

### `app/services/`

#### What?
Business logic layer that handles external API calls and calculations. Keeps routes thin and focused.

#### Why?
| Without Services | With Services |
|------------------|---------------|
| API calls scattered in routes | Centralized, reusable |
| Hard to test | Easy to mock/test |
| Duplicate code | DRY principle |
| Routes become bloated | Routes stay thin |

#### Services Overview

**PriceFetcher** (`price_fetcher.py`)
Fetches live prices from external APIs.

| Method | Purpose |
|--------|---------|
| `get_stock_price(symbol)` | Fetch single stock price |
| `get_multiple_stock_prices(symbols)` | Fetch multiple stocks in PARALLEL |
| `get_mf_nav(scheme_code)` | Fetch single MF NAV |
| `get_multiple_mf_navs(codes)` | Fetch multiple MFs in PARALLEL |
| `search_mutual_funds(query)` | Search MFs by name |

**PortfolioStats** (`portfolio_stats.py`)
Combines database holdings with live prices.

| Method | Purpose |
|--------|---------|
| `enrich_holdings_with_prices(holdings)` | Add live prices to holdings |
| `calculate_summary(holdings)` | Total invested, P&L, etc. |
| `calculate_asset_allocation(holdings)` | Stock vs MF percentage |
| `get_top_holdings(holdings, limit)` | Top N by value |

#### Key Concepts

**Parallel API Calls**
```python
# Sequential: 1500ms for 3 stocks
for symbol in ["INFY", "TCS", "HDFC"]:
    await get_stock_price(symbol)

# Parallel: ~500ms for 3 stocks
tasks = [get_stock_price(s) for s in symbols]
results = await asyncio.gather(*tasks)
```

**Error Handling**
```python
try:
    response = await client.get(url)
except httpx.TimeoutException:
    return None  # Don't crash, return None

# UI shows "Price unavailable" for failed ones

```

### `app/routers/`

#### What?
Endpoint handlers that define URLs and request/response logic. Each router handles a specific feature area.

#### Why?
| Approach | Problem |
|----------|---------|
| All routes in one file | 500+ lines, hard to navigate |
| One file per feature | Clean, organized, maintainable |

#### Routers Overview

| Router | Prefix | Purpose |
|--------|--------|---------|
| `dashboard.py` | `/` | Main dashboard, combined stats |
| `stocks.py` | `/stocks` | Stock CRUD operations |
| `mutualfunds.py` | `/mutualfunds` | MF CRUD + search |

#### Endpoints Summary

**Dashboard**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard HTML page |
| GET | `/api/dashboard/stats` | Stats as JSON |

**Stocks**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stocks` | Stocks list page |
| GET | `/stocks/add` | Add stock form |
| POST | `/stocks/add` | Handle form submission |
| POST | `/stocks/api` | Create stock (JSON) |
| DELETE | `/stocks/api/{id}` | Delete stock |
| GET | `/stocks/api/{id}/price` | Get live price |

**Mutual Funds**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/mutualfunds` | MF list page |
| GET | `/mutualfunds/add` | Add MF form |
| POST | `/mutualfunds/add` | Handle form submission |
| GET | `/mutualfunds/api/search?q=` | Search MFs |
| POST | `/mutualfunds/api` | Create MF (JSON) |
| DELETE | `/mutualfunds/api/{id}` | Delete MF |
| GET | `/mutualfunds/api/{id}/nav` | Get live NAV |

#### Key Concepts

**Router Prefix**
```python
router = APIRouter(prefix="/stocks")
# All routes start with /stocks
```

**Dependency Injection**
```python
async def endpoint(db: AsyncSession = Depends(get_db)):
    # db is auto-provided, auto-committed, auto-closed
```

### `app/templates/`

#### What?
Jinja2 HTML templates that render the user interface. Data from Python is injected into HTML placeholders.

#### Why Jinja2?
| Feature | Syntax | Example |
|---------|--------|---------|
| Variables | `{{ var }}` | `{{ stock.name }}` |
| Loops | `{% for %}` | `{% for stock in stocks %}` |
| Conditionals | `{% if %}` | `{% if pnl > 0 %}` |
| Inheritance | `{% extends %}` | `{% extends "base.html" %}` |
| Blocks | `{% block %}` | `{% block content %}` |
| Filters | `{{ var \| filter }}` | `{{ name \| upper }}` |

#### Template Hierarchy
base.html (parent) 
├── dashboard.html 
├── stocks/ │ 
  ├── list.html 
│ └── add.html 
└── mutualfunds/ 
  ├── list.html 
  └── add.html

### `app/static/css/style.css`

#### What?
Main stylesheet controlling all visual aspects — colors, spacing, layout, typography.

#### Why CSS Variables?
```css
:root {
    --color-primary: #2d6a4f;
}
```

Change once → updates everywhere. Easy theming.
**Color Scheme**
| Variable | Color | Usage |
|--------|------|-------------|
|--color-primary |	#2d6a4f (Forest Green) |	Buttons, links, sidebar
|--color-profit |	#198754 (Green) |	Positive P&L
|--color-loss |	#dc3545 (Red)	| Negative P&L
|--color-background |#f8f9fa (Light Gray) |	Page background
|--color-surface |	#ffffff (White) |	Cards, forms

**Key Classes**
| Class | Purpose |
|--------|--------|
|.app-container | Flex container for sidebar + main
|.sidebar | Fixed left navigation
|.main-content | Scrollable content area
|.metrics-row |	3-column grid for metric cards
|.content-row |	3-column grid for content cards
|.profit / .loss |	Green/red text colors
|.btn-* | Button variants
|.modal	| Delete confirmation popup

**Responsive Breakpoints**
| Width | Layout Change |
|--------|--------|
|> 1024px | 3 columns
|768-1024px | 2 columns, stacked content
|< 768px | Single column, top navigation

## API Reference

### Pages (HTML)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET | `/stocks` | Stocks listing |
| GET | `/stocks/add` | Add stock form |
| GET | `/mutualfunds` | Mutual funds listing |
| GET | `/mutualfunds/add` | Add MF form |

### API (JSON)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/stocks` | Create stock |
| DELETE | `/api/stocks/{id}` | Delete stock |
| POST | `/api/mutualfunds` | Create MF |
| DELETE | `/api/mutualfunds/{id}` | Delete MF |
| GET | `/api/prices/{symbol}` | Fetch live price |

### External APIs Used

**Stock Prices (NSE/BSE):**
```
GET https://nse-api-khaki.vercel.app/stock?symbol=INFY&res=num

Response: { "data": { "last_price": 1520.45, ... } }
```

**Mutual Fund NAV:**
```
GET https://api.mfapi.in/mf/120503/latest

Response: { "data": [{ "nav": "52.1045" }] }
```

**MF Search:**
```
GET https://api.mfapi.in/mf/search?q=axis%20bluechip

Response: [{ "schemeCode": 120503, "schemeName": "Axis Bluechip..." }]
```

---

## Development Notes

### Database Location
`stealthoak.db` is created in the project root. It's git-ignored.
To reset: delete the file and restart the app.

### Price Fetching Strategy
- **Phase 0:** Fetch on every page load (parallel calls)
- **Phase 1+:** Cache for 15 min + manual refresh button

### Adding New Features
1. Create model in `app/models/`
2. Create schema in `app/schemas/`
3. Create router in `app/routers/`
4. Add service logic in `app/services/`
5. Create template in `app/templates/`
6. Update this README!

---

## License

Personal project. Not for distribution.

---

*Last updated: 2026-03-22*