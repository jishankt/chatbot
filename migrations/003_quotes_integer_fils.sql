-- Migration 003: Dual-write integer fils and quote snapshot metadata
ALTER TABLE quotes ADD COLUMN subtotal_fils INTEGER;
ALTER TABLE quotes ADD COLUMN vat_fils INTEGER;
ALTER TABLE quotes ADD COLUMN total_fils INTEGER;
ALTER TABLE quotes ADD COLUMN catalog_version TEXT DEFAULT '2026.1';
ALTER TABLE quotes ADD COLUMN expires_at TIMESTAMP;
