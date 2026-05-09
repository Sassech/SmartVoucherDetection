"""Seed determinista — IDs y datos del tenant `system` de Fase 1.

Por que UUIDs hardcoded (no env, no generados al vuelo):
- Determinismo cross-environment: dev, staging, prod, CI usan el mismo ID.
  Esto permite que tests de integracion no inventen su propio "system user"
  y que un dump de prod restaurado en dev tenga referencias intactas.
- Reproducibilidad: si la migracion corre dos veces (o se reaplica en una
  DB nueva), el `INSERT ... ON CONFLICT DO NOTHING` es idempotente porque
  el ID es estable.
- Fase 4 lo deprecara: cuando arranquemos auth real, el seed sigue ahi
  como tenant interno (cron jobs, validaciones automaticas que no tienen
  usuario humano detras). NO se borra.

Estos UUIDs se generaron con `uuid_utils.compat.uuid7()` el 2026-05-09 y
NO deben cambiarse jamas. Si alguna vez hace falta rotarlos, hay que
hacer DATA migration explicita, no editar este archivo.
"""

from __future__ import annotations

import uuid

# Tenant "system" — usado por todo lo que no tenga organizacion asignada
# (cron jobs, seed de Fase 1 sin auth, scripts internos).
SYSTEM_ORG_ID: uuid.UUID = uuid.UUID("019e0d75-323e-74b3-a249-90828e8673e6")
SYSTEM_ORG_NOMBRE: str = "system"
SYSTEM_ORG_PLAN: str = "empresarial"

# Usuario "system" — autor de comprobantes en Fase 1 (sin auth real).
# Pertenece a SYSTEM_ORG_ID.
SYSTEM_USER_ID: uuid.UUID = uuid.UUID("019e0d75-323e-74b3-a249-909b3f77ee9f")
SYSTEM_USER_NOMBRE: str = "system"
SYSTEM_USER_CORREO: str = "system@smartvoucher.local"
SYSTEM_USER_ROL: str = "admin"
# Bcrypt hash REAL (cost 12) de la cadena `!disabled-system-account-fase1`.
# Verificable con `bcrypt.checkpw(...)` — no es un placeholder fake. Se eligio
# una password fija y conocida por dos razones:
#   1. Si alguien con DB access intenta loguearse con ese string, SI funciona
#      el hash, pero la cuenta no tiene ningun endpoint expuesto en Fase 1.
#   2. En Fase 4 cuando agregemos auth real, esta cuenta queda DESACTIVADA
#      via flag explicito (no por hash invalido) — patron mas claro.
# NOTA: bcrypt 4.x + passlib 1.7 son incompatibles (issue conocido). Por eso
# el seed se genero con `bcrypt.hashpw` directo, no via passlib.
SYSTEM_USER_PASSWORD_HASH: str = (
    "$2b$12$55kcgfnV37U7tBPMb9NgBe9DABmhO0Z7/ZaqHsmhVDLQNlFhqtZsm"
)
