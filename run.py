# ============================================
# StealthOak - Entry Point
# ============================================

"""
Run the StealthOak application.

Usage:
    python run.py

Or with uvicorn directly:
    uvicorn run:app --reload

The app will be available at:
    http://127.0.0.1:8000
"""

import uvicorn

from app import app


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════╗
    ║                                           ║
    ║   🌳 StealthOak                           ║
    ║   ─────────────────────────────────────   ║
    ║   Silent. Patient. Compounds.             ║
    ║                                           ║
    ║   Starting server at:                     ║
    ║   http://127.0.0.1:8000                   ║
    ║                                           ║
    ║   Press Ctrl+C to stop                    ║
    ║                                           ║
    ╚═══════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "run:app",          # Import path to app
        host="127.0.0.1",   # Localhost only
        port=8000,          # Port number
        reload=True,        # Auto-reload on code changes
        log_level="info",   # Logging verbosity
    )
