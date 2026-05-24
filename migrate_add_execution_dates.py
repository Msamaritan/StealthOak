"""
Migration script to add execution_dates column to active_sips table
Run this once: python migrate_add_execution_dates.py
"""
import sqlite3
import os
from config import settings

# Parse SQLite database path from settings
db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")

print(f"Connecting to database: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(active_sips)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "execution_dates" in columns:
        print("✓ Column 'execution_dates' already exists in active_sips table")
    else:
        print("Adding column 'execution_dates' to active_sips table...")
        cursor.execute("""
            ALTER TABLE active_sips 
            ADD COLUMN execution_dates VARCHAR(255) NULL
        """)
        conn.commit()
        print("✓ Column 'execution_dates' added successfully!")
    
    cursor.close()
    conn.close()
    print("\nMigration complete!")
    
except Exception as e:
    print(f"❌ Error during migration: {e}")
    import traceback
    traceback.print_exc()
