-- Author: Brad Duy - AI Expert
-- Tool Registry table with full-text search via tsvector/GIN
-- Supports multi-tenant tool discovery

CREATE TABLE IF NOT EXISTS tool_registry (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       TEXT        NOT NULL,
    namespace       TEXT        NOT NULL DEFAULT '',
    name            TEXT        NOT NULL,
    description     TEXT        NOT NULL DEFAULT '',
    tags            TEXT[]      NOT NULL DEFAULT '{}',
    examples        TEXT[]      NOT NULL DEFAULT '{}',
    parameters_schema JSONB     NOT NULL DEFAULT '{}',
    output_schema   JSONB       NULL,
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    risk_level      SMALLINT    NOT NULL DEFAULT 1
                    CHECK (risk_level BETWEEN 1 AND 4),
    auth_type       TEXT        NULL,
    endpoint        TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Generated tsvector column for full-text search
    search_tsv      TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(array_to_string(tags, ' '), '')), 'C')
    ) STORED,

    UNIQUE (tenant_id, namespace, name)
);

-- GIN index on the tsvector column for fast full-text search
CREATE INDEX IF NOT EXISTS idx_tool_registry_search
    ON tool_registry USING GIN (search_tsv);

-- B-tree indexes for common filters
CREATE INDEX IF NOT EXISTS idx_tool_registry_tenant
    ON tool_registry (tenant_id);

CREATE INDEX IF NOT EXISTS idx_tool_registry_tenant_ns
    ON tool_registry (tenant_id, namespace);

CREATE INDEX IF NOT EXISTS idx_tool_registry_enabled
    ON tool_registry (tenant_id, enabled)
    WHERE enabled = TRUE;

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_tool_registry_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tool_registry_updated ON tool_registry;
CREATE TRIGGER trg_tool_registry_updated
    BEFORE UPDATE ON tool_registry
    FOR EACH ROW
    EXECUTE FUNCTION update_tool_registry_timestamp();

-- Example seed data (optional, remove for production)
-- INSERT INTO tool_registry (tenant_id, namespace, name, description, tags, parameters_schema, risk_level)
-- VALUES
--   ('default', 'weather', 'get_weather', 'Get current weather for a city',
--    ARRAY['weather','forecast'], '{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}', 1),
--   ('default', 'math', 'calculate', 'Evaluate a math expression',
--    ARRAY['math','calculator'], '{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}', 1);
