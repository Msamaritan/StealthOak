"""
Migration script to add compute_investment_gain column to insurance_policies table.
Run this once: python migrate_add_compute_investment_gain.py
"""
import sqlite3

from config import settings


db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")

print(f"Connecting to database: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(insurance_policies)")
    columns = [col[1] for col in cursor.fetchall()]

    if "compute_investment_gain" in columns:
        print("Column 'compute_investment_gain' already exists in insurance_policies table")
    else:
        print("Adding column 'compute_investment_gain' to insurance_policies table...")
        cursor.execute(
            """
            ALTER TABLE insurance_policies
            ADD COLUMN compute_investment_gain BOOLEAN NOT NULL DEFAULT 0
            """
        )
        conn.commit()
        print("Column 'compute_investment_gain' added successfully")

    cursor.close()
    conn.close()
    print("Migration complete")

except Exception as e:
    print(f"Error during migration: {e}")
    import traceback

    traceback.print_exc()
