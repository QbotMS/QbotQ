-- Centrum powiadomien v2 (2026-10-08): krzyzyk = usun z listy, wiersz zostaje do Historii
ALTER TABLE qbot_v2.notif ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMPTZ;
