-- ============================================================================
-- SmartVoucherDetection — inicialización de PostgreSQL
-- Se ejecuta automáticamente la PRIMERA vez que se inicializa el volumen
-- de datos (montado en /docker-entrypoint-initdb.d/ desde docker-compose.yml).
--
-- Si necesitás re-aplicar tras un cambio: `docker compose down -v && up -d`.
-- ============================================================================

-- Búsqueda por similitud (Levenshtein-like sobre trigramas) — crítico para
-- la detección de duplicados en Fase 2 (scoring de referencias).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- gen_random_uuid() y funciones criptográficas — usado para PKs y hashes.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Normalización sin acentos para matching insensible a diacríticos.
CREATE EXTENSION IF NOT EXISTS unaccent;
