"""
Migration script to remove tax_claim_amount from insurance_premium_payments table.

Run once:
    python migrate_remove_tax_claim.py
"""

import sqlite3
from config import settings


def main() -> None:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='insurance_premium_payments'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        print("insurance_premium_payments table does not exist. Nothing to migrate.")
        conn.close()
        return

    cursor.execute("PRAGMA table_info(insurance_premium_payments)")
    columns = [row[1] for row in cursor.fetchall()]

    if "tax_claim_amount" not in columns:
        print("tax_claim_amount column already removed. No changes needed.")
        conn.close()
        return

    print("Removing tax_claim_amount column from insurance_premium_payments...")

    cursor.execute("PRAGMA foreign_keys=OFF")
    conn.commit()

    # Create replacement table without tax_claim_amount
    cursor.execute(
        """
        CREATE TABLE insurance_premium_payments_new (
            id INTEGER PRIMARY KEY,
            policy_id INTEGER NOT NULL,
            payment_date DATE NOT NULL,
            amount FLOAT NOT NULL,
            payment_mode VARCHAR(30),
            reference_no VARCHAR(60),
            notes VARCHAR(255),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_id) REFERENCES insurance_policies(id) ON DELETE CASCADE
        )
        """
    )

    # Copy existing data, excluding tax_claim_amount
    cursor.execute(
        """
        INSERT INTO insurance_premium_payments_new (
            id, policy_id, payment_date, amount, payment_mode, reference_no, notes, created_at
        )
        SELECT
            id, policy_id, payment_date, amount, payment_mode, reference_no, notes, created_at
        FROM insurance_premium_payments
        """
    )

    # Replace old table
    cursor.execute("DROP TABLE insurance_premium_payments")
    cursor.execute("ALTER TABLE insurance_premium_payments_new RENAME TO insurance_premium_payments")

    # Recreate foreign key index
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_insurance_premium_payments_policy_id ON insurance_premium_payments (policy_id)"
    )

    conn.commit()
    cursor.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()

    print("Migration complete. tax_claim_amount column removed.")


if __name__ == "__main__":
    main()
