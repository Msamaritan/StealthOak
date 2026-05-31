"""
Migration script for insurance schema updates.

Changes:
1. Removes tax_section column from insurance_policies.
2. Adds last_premium_payment_date column.
3. Adds total_premium_amount column.
4. Adds policy_term column (in years).

Run once:
    python migrate_insurance_schema.py
"""

import sqlite3
from config import settings


def main() -> None:
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='insurance_policies'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        print("insurance_policies table does not exist yet. Nothing to migrate.")
        conn.close()
        return

    cursor.execute("PRAGMA table_info(insurance_policies)")
    columns = [row[1] for row in cursor.fetchall()]

    needs_rebuild = "tax_section" in columns
    needs_last_payment = "last_premium_payment_date" not in columns
    needs_total_premium = "total_premium_amount" not in columns
    needs_policy_term = "policy_term" not in columns

    if not needs_rebuild and not needs_last_payment and not needs_total_premium and not needs_policy_term:
        print("Schema already up to date. No changes needed.")
        conn.close()
        return

    print("Applying insurance schema migration...")

    cursor.execute("PRAGMA foreign_keys=OFF")
    conn.commit()

    # Create replacement table with the latest schema.
    cursor.execute(
        """
        CREATE TABLE insurance_policies_new (
            id INTEGER PRIMARY KEY,
            policy_name VARCHAR(100) NOT NULL,
            provider VARCHAR(80) NOT NULL,
            policy_category VARCHAR(20) NOT NULL DEFAULT 'other',
            policy_type VARCHAR(30) NOT NULL DEFAULT 'traditional',
            policy_number VARCHAR(60) NOT NULL,
            insured_person VARCHAR(100) NOT NULL,
            nominee VARCHAR(100),
            start_date DATE NOT NULL,
            maturity_date DATE,
            policy_term INTEGER,
            premium_amount FLOAT NOT NULL,
            premium_frequency VARCHAR(20) NOT NULL DEFAULT 'yearly',
            last_premium_payment_date DATE,
            total_premium_amount FLOAT,
            sum_assured FLOAT,
            current_value FLOAT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            notes VARCHAR(255),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Copy existing data, defaulting new columns when absent.
    select_last_payment = (
        "last_premium_payment_date"
        if "last_premium_payment_date" in columns
        else "NULL"
    )
    select_total_premium = (
        "total_premium_amount"
        if "total_premium_amount" in columns
        else "NULL"
    )
    select_policy_term = (
        "policy_term"
        if "policy_term" in columns
        else "NULL"
    )

    cursor.execute(
        f"""
        INSERT INTO insurance_policies_new (
            id, policy_name, provider, policy_category, policy_type,
            policy_number, insured_person, nominee,
            start_date, maturity_date, policy_term,
            premium_amount, premium_frequency,
            last_premium_payment_date, total_premium_amount,
            sum_assured, current_value,
            is_active, notes,
            created_at, updated_at
        )
        SELECT
            id, policy_name, provider, policy_category, policy_type,
            policy_number, insured_person, nominee,
            start_date, maturity_date, {select_policy_term},
            premium_amount, premium_frequency,
            {select_last_payment}, {select_total_premium},
            sum_assured, current_value,
            is_active, notes,
            created_at, updated_at
        FROM insurance_policies
        """
    )

    # Replace old table.
    cursor.execute("DROP TABLE insurance_policies")
    cursor.execute("ALTER TABLE insurance_policies_new RENAME TO insurance_policies")

    # Recreate index that existed on policy_number.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_insurance_policies_policy_number ON insurance_policies (policy_number)"
    )

    conn.commit()
    cursor.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()

    print("Insurance schema migration complete.")


if __name__ == "__main__":
    main()
