-- Migration 002: Add optimistic locking version column to conversation_states
ALTER TABLE conversation_states ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
