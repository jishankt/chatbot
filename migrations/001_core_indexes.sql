-- migrations/001_core_indexes.sql
-- Creates essential compound indexes to eliminate full table scans on messages, handoffs, quotes, and leads

CREATE INDEX IF NOT EXISTS idx_messages_sender_timestamp ON messages(sender_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_handoffs_sender_status ON handoffs(sender_id, status);
CREATE INDEX IF NOT EXISTS idx_quotes_sender_created ON quotes(sender_id, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_sender ON leads(sender_id);
