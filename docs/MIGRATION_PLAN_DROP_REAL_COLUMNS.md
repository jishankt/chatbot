# Migration Plan: Dropping REAL Monetary Columns in Quotes Table

## 1. Executive Summary
To prevent floating-point rounding inaccuracies in commercial quotations, the Sales AI database has completed Phase 1 of the monetary precision hardening: **Dual-Write Architecture (Migration 003)**.
Both legacy floating-point columns (`subtotal`, `vat_amount`, `total`) and exact integer fils columns (`subtotal_fils`, `vat_fils`, `total_fils`, where 1 AED = 100 fils) are actively maintained.

This document outlines the phased plan to complete the transition and drop the legacy `REAL` columns in production.

---

## 2. Transition Phases & Milestones

### Phase 1: Dual-Write & Historical Backfill (COMPLETED)
- **Status**: Complete.
- Schema updated via `migrations/003_quotes_integer_fils.sql`.
- In-flight writes write both REAL and INTEGER fils calculated with `Decimal.quantize(..., rounding=ROUND_HALF_UP)`.
- Backfill script `scripts/backfill_quote_fils.py` executed across all historical rows.
- Automated mismatch checker `scripts/check_quote_fils_mismatch.py` validates mathematical parity across 100% of rows.

### Phase 2: Read Cutover (Next Milestone)
- All query readers in `app/storage/quotes.py` and downstream report generators switch primary reads to `subtotal_fils`, `vat_fils`, and `total_fils`.
- Presentation layer derives AED strings using exact division: `f"{Decimal(total_fils) / 100:.2f} AED"`.
- Continuous cron job runs `check_quote_fils_mismatch.py` daily to verify zero divergence during dual-write.

### Phase 3: Final Schema Migration (Drop REAL Columns)
SQLite does not support `ALTER TABLE DROP COLUMN` on legacy table definitions with certain constraints or triggers without recreating the table. Therefore, Migration 004 will perform an atomic table replacement using standard SQLite migration best practices:

```sql
-- Migration 004: Drop legacy REAL columns from quotes table
BEGIN TRANSACTION;

-- 1. Create clean target table with INTEGER fils columns only
CREATE TABLE quotes_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id TEXT UNIQUE NOT NULL,
    sender_id TEXT,
    customer_name TEXT,
    phone TEXT,
    items_json TEXT NOT NULL,
    subtotal_fils INTEGER NOT NULL,
    vat_fils INTEGER,
    total_fils INTEGER NOT NULL,
    catalog_version TEXT DEFAULT '2026.1',
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Copy data across
INSERT INTO quotes_v2 (
    id, quote_id, sender_id, customer_name, phone, items_json,
    subtotal_fils, vat_fils, total_fils, catalog_version, expires_at, created_at
)
SELECT 
    id, quote_id, sender_id, customer_name, phone, items_json,
    subtotal_fils, vat_fils, total_fils, catalog_version, expires_at, created_at
FROM quotes;

-- 3. Replace old table
DROP TABLE quotes;
ALTER TABLE quotes_v2 RENAME TO quotes;

-- 4. Rebuild indexes
CREATE INDEX idx_quotes_sender_id ON quotes(sender_id);
CREATE INDEX idx_quotes_created_at ON quotes(created_at);
CREATE INDEX idx_quotes_quote_id ON quotes(quote_id);

COMMIT;
```

### Phase 4: Post-Migration Validation & Rollback Strategy
1. **Pre-Migration Safety**: Run `sqlite3 data/sales_ai.db ".backup data/sales_ai.db.pre_004.bak"`.
2. **Execution**: Execute migration inside an exclusive SQLite transaction.
3. **Integrity Check**: Execute `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`.
4. **Rollback Guarantee**: In case of failure during execution, SQLite transaction rollback occurs automatically. If detected post-commit, swap back from `.pre_004.bak` within 60 seconds.
