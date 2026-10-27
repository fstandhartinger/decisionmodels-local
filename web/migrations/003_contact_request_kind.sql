ALTER TABLE hardware_inquiries ADD COLUMN IF NOT EXISTS request_kind text NOT NULL DEFAULT 'hardware' CHECK (request_kind IN ('hardware', 'local'));
