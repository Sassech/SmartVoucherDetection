# Exploración: Motor de Detección de Duplicados — Fase 2

**Fecha:** 2026-05-09  
**Generado por:** sdd-explore  
**Objetivo:** Análisis consolidado de Fase 2 para que el orquestador proponga un plan de implementación concreto.

---

## 1. Tareas de Fase 2 según PROGRESO.md

> Estado actual: **todas pendientes `[ ]`**. Fase 1 marcada completada. Próximo paso: `2.1`.

### 2.1 Detección Capa 1 — Hash exacto (Redis)
- `[ ] 2.1.1` Cliente Redis async (`services/cache_service.py`)
- `[ ] 2.1.2` Función `check_hash(hash: str) -> Optional[ComprobanteId]`
- `[ ] 2.1.3` TTL 7 días, key pattern `comp:hash:{sha256}`

### 2.2 Detección Capa 2 — Campos críticos exactos (Postgres)
- `[ ] 2.2.1` Query: `WHERE referencia = ? AND monto = ? AND fecha = ?`
- `[ ] 2.2.2` Índice compuesto en `(referencia, monto, fecha_deposito)` — agregar a migración
- `[ ] 2.2.3` Si match: marcar como `duplicado`, registrar en `Validacion`

### 2.3 Detección Capa 3 — Scoring ponderado (`services/duplicate_service.py`)
- `[ ] 2.3.1` `S_ref` con `python-Levenshtein.ratio()` (peso 0.35)
- `[ ] 2.3.2` `S_texto` con `TfidfVectorizer + cosine_similarity` (peso 0.30)
- `[ ] 2.3.3` `S_monto` numérica normalizada (peso 0.20)
- `[ ] 2.3.4` `S_fecha` por días en ventana de 30 (peso 0.15)
- `[ ] 2.3.5` Función `compute_score(nuevo, existente) -> float`
- `[ ] 2.3.6` Clasificador: ≥0.90 duplicado, 0.75–0.90 sospechoso, <0.75 válido

### 2.4 Celery — modo asíncrono
- `[ ] 2.4.1` `tasks/process_slip.py` — task Celery con todo el flujo
- `[ ] 2.4.2` Endpoint `POST /upload-slip/async` → encola → responde `{task_id, status: "queued"}`
- `[ ] 2.4.3` Endpoint `GET /status/{task_id}` → consulta estado en Redis
- `[ ] 2.4.4` Worker: `celery -A api.tasks worker --concurrency=4`
- `[ ] 2.4.5` Servicio Celery agregado al `docker-compose.yml`

### 2.5 Endpoints adicionales
- `[ ] 2.5.1` `POST /validate/{id}` — CU-02 validación manual
- `[ ] 2.5.2` `GET /report` — reportes (válidos/duplicados/sospechosos/tiempo promedio)

### 2.6 Diagrama de estados — implementar transiciones
- `[ ] 2.6.1` Máquina de estados en `services/state_machine.py` siguiendo `cosas/diagrama_estados.svg`
- `[ ] 2.6.2` Tests: cada transición posible

### 2.7 Criterios de Aceptación de Fase 2
- `[ ] 2.7.1` Detección correcta ≥90% en dataset (20 únicos + 10 duplicados + 10 sospechosos)
- `[ ] 2.7.2` Hash exacto detectado en <100ms (cache Redis)
- `[ ] 2.7.3` Flujo síncrono completo ≤5s
- `[ ] 2.7.4` Task Celery completa en <30s
- `[ ] 2.7.5` `POST /validate/{id}` actualiza estado correctamente en 100% de tests

---

## 2. Especificación detallada según plan_desarrollo.md (Fase 2)

### 2.1 Estrategia de detección en cascada

Las 3 capas operan en cascada — si una capa clasifica con certeza, las posteriores NO se ejecutan:

| # | Nivel | Herramienta | Acción si hay match |
|---|-------|-------------|---------------------|
| 1 | Hash exacto | Redis lookup SHA-256 | DUPLICADO CONFIRMADO → retornar sin más cómputo |
| 2 | Campos críticos exactos | PostgreSQL: `referencia + monto + fecha` | DUPLICADO CONFIRMADO → guardar Validacion y retornar |
| 3 | Scoring ponderado | Levenshtein + TF-IDF coseno + Jaccard | Score ≥0.90 → Duplicado / 0.75-0.90 → Sospechoso / <0.75 → Válido |

### 2.2 Fórmula de scoring ponderado

```
Score = w₁×S_ref + w₂×S_texto + w₃×S_monto + w₄×S_fecha
```

| Variable | Peso inicial | Librería | Justificación |
|----------|-------------|----------|---------------|
| `S_ref` | w₁ = 0.35 | `python-Levenshtein.ratio()` | Mayor discriminación (ID único de transacción) |
| `S_texto` | w₂ = 0.30 | `sklearn.TfidfVectorizer + cosine_similarity` | Detecta modificaciones en estructura global |
| `S_monto` | w₃ = 0.20 | `1 - |a-b| / max(a,b)` | Relevante pero no único (pagos repetidos posibles) |
| `S_fecha` | w₄ = 0.15 | Diferencia en días / ventana 30 días | Contexto temporal; varios depósitos/día posibles |

**Clasificador:**
- Score ≥ 0.90 → `duplicado`
- 0.75 ≤ Score < 0.90 → `sospechoso`
- Score < 0.75 → `valido`

**Optimización Redis:** Antes del scoring, consultar Redis con hash SHA-256. Cache hit = <100ms sin llamar a glm-ocr ni ejecutar scoring. TTL: 7 días.

### 2.3 Diseño de la tarea Celery

**Cuándo usar modo asíncrono:**
- Llamadas desde WooCommerce (el usuario no espera)
- Procesamiento por lotes
- Cuando tiempo estimado > 3 segundos (autodetección por tamaño/resolución)

**Endpoints asíncronos nuevos en Fase 2:**
- `POST /upload-slip/async` → encola tarea → `{task_id, status: "queued"}`
- `GET /status/{task_id}` → consulta Redis por estado → `{status: pending|processing|done|error, result?}`
- Worker: `celery -A api.tasks worker --loglevel=info --concurrency=4`

### 2.4 Transiciones de estados (máquina de estados)

El diagrama `cosas/diagrama_estados.svg` define:
- **Estados terminales** (borde doble): `Válido`, `Duplicado`, `Error`
- **Estado `Error` (añadido):** recibe transiciones desde `Procesando` (fallo OCR) y `Comparando` (fallo scoring)
- **Transiciones de `EnRevision`:** tiene salidas hacia `Válido` (confirmar) y `Duplicado` (rechazar)

**Flujo completo:**
```
recibido → procesando → comparando → {valido | sospechoso → en_revision → {valido|duplicado} | duplicado | error}
```

### 2.5 Redis key patterns y TTL

- **Capa 1 (hash exacto):** `comp:hash:{sha256}` — TTL 7 días
- **Estado Celery:** `{task_id}` — con campos `status`, `result` — el plan no especifica TTL explícito (asumir 24h-7d)

### 2.6 Endpoints actualizados en Fase 2

| Endpoint | Cambio |
|----------|--------|
| `POST /upload-slip` | Añade flujo completo de 3 capas de detección |
| `POST /upload-slip/async` | NUEVO — versión Celery |
| `GET /status/{task_id}` | NUEVO — consulta Celery/Redis |
| `POST /validate/{id}` | NUEVO — CU-02 validación manual |
| `GET /report` | NUEVO — estadísticas agregadas |

---

## 3. Qué está construido en Fase 1 y puede reutilizar Fase 2

### 3.1 `services/cache_service.py` — estado actual vs. lo que necesita Fase 2

**Ya existe:**
- `_get_client() -> Redis` — pool global lazy, `decode_responses=False`
- `ping(timeout_s: float) -> bool` — para health check; nunca propaga excepciones
- `close() -> None` — idempotente, para shutdown y teardown de tests

**Comentario del propio docstring en `cache_service.py`:**
> "El resto de la API pública (`check_hash`, set/get con TTL, etc.) llega en Fase 2.1.1"

**Lo que hay que agregar en 2.1:**
- `check_hash(hash: str) -> str | None` — GET de `comp:hash:{hash}` → devuelve `id_comprobante` como str si existe, `None` si no
- `set_hash(hash: str, id_comprobante: str, ttl_days: int = 7) -> None` — SETEX de `comp:hash:{hash}` con TTL en segundos
- `get_task_status(task_id: str) -> dict | None` — para el endpoint `GET /status/{task_id}` (o puede usar `celery.AsyncResult` directamente — ver §4 gaps)

**Patrón establecido a respetar:**
- Las nuevas funciones NUNCA propagan excepciones (igual que `ping`)
- `decode_responses=False` — los callers deciden qué esperar
- Pool lazy, no instanciar al import

### 3.2 Modelo `Comprobante` — campos relevantes por capa

| Capa | Campos del modelo que se usan |
|------|-------------------------------|
| Capa 1 (hash) | `hash_documento` (String 64, UNIQUE — ya indexado) |
| Capa 2 (campos exactos) | `referencia`, `monto` (Numeric 15,2), `fecha_deposito` (Date) |
| Capa 3 (scoring) | `referencia`, `texto_extraido`, `monto`, `fecha_deposito` |
| Estado machine | `estado_actual` (CHECK constraint con todos los estados válidos) |

**Índice pendiente (ya documentado en el modelo):**
```python
# models/comprobante.py línea 18-19:
# Indice compuesto `(referencia, monto, fecha_deposito)` queda para 2.2.2 cuando
# se implemente Capa 2.
```

**Gotcha:** `texto_extraido` se inserta como `None` en Fase 1 (`upload.py` línea 204: `texto_extraido=None`). La Capa 3 necesita `texto_extraido` para TF-IDF — si la columna es NULL, `S_texto` debería tratarse como 0 o computarse sólo sobre `referencia`. **Esta ambigüedad requiere decisión antes de implementar 2.3.2.**

### 3.3 Modelo `Validacion` — listo para Fase 2

El modelo ya tiene todo lo necesario:
- `id_comprobante` (FK con CASCADE)
- `id_usuario` (nullable — detecciones automáticas sin autor)
- `score_similitud` (Float, CHECK [0,1] OR NULL)
- `clasificacion` CHECK: `('valido', 'sospechoso', 'duplicado')`
- `metodo_deteccion` CHECK: `('hash_exacto', 'campos_exactos', 'scoring_ponderado', 'manual')`

**No hay nada que agregar al modelo para Fase 2.** Solo falta la lógica de negocio que lo puebla.

**Relación faltante a analizar:** `Validacion` no tiene FK a un "comprobante candidato" (el original del cual es duplicado). El plan no lo menciona explícitamente, pero el endpoint de validación manual (`POST /validate/{id}`) y la vista side-by-side de Fase 4 podrían requerirlo. **Decisión pendiente: ¿agregar `id_comprobante_original` nullable a `Validacion`?**

### 3.4 Pipeline `routers/upload.py` — dónde insertar la deduplicación

El pipeline actual (Fase 1) tiene estos pasos numerados:

```
1. _read_upload (bytes + cap)
2. validate_mime (libmagic)
3. compute_hash (SHA-256)
4. _find_existing_by_hash → 409 si ya existe  ← HOY: solo DB, sin Redis
5. save_upload (filesystem, write atómico)
6. pdf_to_image (si PDF)
7. preprocess + to_base64 (OpenCV)
8. extract_fields (OCR — llama-server)
9. parse_* + normalize_banco
10. INSERT Comprobante (estado="recibido")
```

**Hooks de Fase 2:**

| Paso nuevo | Dónde en el pipeline | Qué hace |
|-----------|---------------------|----------|
| Capa 1 (Redis) | Reemplaza paso 4 | `cache_service.check_hash()` antes de consultar DB; si hit → 409 + INSERT Validacion(hash_exacto) |
| Capa 1 (Redis set) | Después de paso 10 | `cache_service.set_hash(hash, id_comprobante)` tras commit exitoso |
| Transición de estado | Reemplaza estado="recibido" hardcoded | `state_machine.transition(comprobante, "procesando")` al inicio, `"comparando"` antes de las capas, `"valido"/"duplicado"/"sospechoso"` al final |
| Capa 2 (Postgres exact) | Entre paso 4 y paso 5 (post-OCR realmente, ver §4) | Query `WHERE referencia=? AND monto=? AND fecha=?` + INSERT Validacion(campos_exactos) |
| Capa 3 (scoring) | Después de Capa 2 | `duplicate_service.compute_score()` → INSERT Validacion(scoring_ponderado) |

**Problema de ordering:** Las Capas 2 y 3 requieren campos normalizados (`referencia`, `monto`, `fecha`) que solo están disponibles DESPUÉS del paso 9 (OCR + parse). El flujo en cascada del plan asume que Capa 1 es pre-OCR (hash en bytes originales) y Capas 2/3 son post-OCR. Esto es consistente con la arquitectura actual.

### 3.5 Patrones de Fase 1 que Fase 2 debe seguir

1. **Tests primero (strict_tdd: true en openspec/config.yaml)** — cada función nueva tiene tests antes de implementación
2. **Mock completo en tests de servicios** — `httpx.MockTransport` para OCR, `monkeypatch` para cache_service
3. **Fixtures de DB** — `db_session` (NullPool, rollback al final) + `client` (ASGI, NO TestClient sync)
4. **No levantar excepciones en wrappers de infra** — `cache_service` nunca propaga
5. **Tipo `Decimal` para montos** — NUNCA float (D-10 + gotcha del `Decimal(0.1)`)
6. **Coverage ≥70% como gate de CI** — actualmente en 96%, no degradar
7. **`CAST(:id AS uuid)`** en migraciones con UUIDs hardcoded (gotcha `text(":id::uuid")`)
8. **`sysmon` core** para coverage correcto con funciones async vía ASGITransport

---

## 4. Gaps y riesgos

### 4.1 Ambigüedades en el plan

| Gap | Descripción | Impacto |
|-----|-------------|---------|
| **`texto_extraido` = NULL** | Fase 1 no persiste el texto raw del LLM. La Capa 3 `S_texto` (TF-IDF coseno, peso 0.30) requiere texto para calcular similitud. Si es NULL en ambos comprobantes, el componente TF-IDF es 0 — pierde el 30% del score. | Alto — afecta precisión del clasificador |
| **`id_comprobante_original` en Validacion** | El modelo no tiene referencia al comprobante del que es duplicado. La Fase 4 requiere vista side-by-side. Sin esto, hay que hacer joins complejos por `metodo_deteccion + fecha`. | Medio — afecta Fase 4, no bloquea Fase 2 |
| **TTL estado Celery en Redis** | El plan especifica TTL 7 días para `comp:hash:{hash}`, pero no especifica TTL para los estados de tareas Celery (`{task_id}`). | Bajo — default de Celery (24h) es razonable |
| **Resultado en `/status/{task_id}`** | El plan dice `{status: pending\|processing\|done\|error, result?}`. No especifica la forma de `result` cuando el estado es `done`. ¿Es el `ComprobanteResponse` completo? ¿Solo el clasificación? | Medio — afecta contrato del endpoint |
| **`POST /validate/{id}` — transiciones permitidas** | CU-02 permite validación manual. ¿Sólo desde `en_revision`? ¿También desde `sospechoso`? El plan dice "validación manual de comprobantes sospechosos" — implica que sólo `sospechoso` → `en_revision` → manual. Pero el state machine puede ser más flexible. | Bajo — clarificar antes de 2.5.1 |
| **`GET /report` — campos exactos** | El plan dice "válidos/duplicados/sospechosos/tiempo promedio". No especifica: ¿por organización? ¿por período? ¿tiempo promedio de qué — del pipeline completo, del scoring, del OCR? | Bajo — pueden asumirse defaults razonables |

### 4.2 Conflictos con decisiones técnicas (D-01 a D-12)

| Conflicto | Detalle |
|-----------|---------|
| **D-10 vs. Capa 3 `S_texto`** | D-10 establece parser tolerante que devuelve `None` ante input inválido. Si `texto_extraido` es `None` (lo es siempre en Fase 1), `S_texto` debe ser explícitamente `0.0`, reduciendo el score máximo alcanzable a 0.70 (w₁+w₃+w₄). Con pesos 0.35+0.20+0.15=0.70, el umbral de 0.90 es **inalcanzable** sin texto. Esto requiere o bien persistir `texto_extraido` o bien ajustar pesos cuando el campo es NULL. |
| **D-11 (409 hardcodeado) vs. Capa 1 Redis** | El 409 actual es directo desde DB. Fase 2.1 agrega Redis delante — si Redis está caído, el fallback debe ser la DB (no romper el pipeline). La función `check_hash` debe ser tolerante a falla de Redis. |
| **D-12 (precisión diferida a Fase 5.1)** | 2.7.1 exige "detección correcta ≥90% en dataset etiquetado (20 únicos + 10 duplicados + 10 sospechosos)". D-12 difirió el bench de precisión a Fase 5.1. **Contradicción**: 2.7.1 pide dataset etiquetado pero D-12 dice que no hay dataset disponible hasta Fase 5.1. Resolución sugerida: el dataset para 2.7.1 puede ser sintético (generado programáticamente con variaciones controladas), distinto del dataset de 100 comprobantes reales de Fase 5.1. |

### 4.3 Dependencias de ordenamiento entre tareas

```
2.6 (state_machine) ← BLOQUEANTE para 2.1, 2.2, 2.3
    La máquina de estados es la que ejecuta las transiciones estado_actual.
    Sin ella, los tests de las capas no pueden validar que el estado del
    comprobante cambia correctamente tras la detección.

2.1 (Redis Capa 1) ← BLOQUEANTE para 2.4 (Celery)
    La tarea Celery (2.4.1) replica el pipeline completo de upload-slip
    sincrono (incluyendo las 3 capas). No se puede escribir la tarea sin
    tener las capas.

2.2 (Alembic migration) ← BLOQUEANTE para 2.2.1/2.2.3
    El índice compuesto necesita una migración Alembic antes de poder
    hacer queries eficientes en Capa 2.

texto_extraido ← DECISIÓN PREVIA a 2.3.2
    Hay que decidir si se persiste en Fase 2 (requiere cambio en upload.py)
    o si S_texto se omite/pondéra a 0 cuando es NULL.
```

### 4.4 Riesgos de complejidad en tests

| Riesgo | Descripción |
|--------|-------------|
| **Celery en tests** | Los tests de `tasks/process_slip.py` requieren o bien un broker Celery real (Redis) o usar `task_always_eager=True` (Celery v5: `CELERY_TASK_ALWAYS_EAGER`). El patrón de conftest actual no configura Celery. |
| **TF-IDF con textos cortos** | `TfidfVectorizer` sobre referencias bancarias cortas (6-20 chars) produce vectores sparse con baja separación. El plan usa TF-IDF para `texto_extraido` (texto completo OCR), no para `referencia`. Pero si `texto_extraido` es NULL, hay que decidir el fallback. |
| **Race condition Capa 1+2** | Si Redis está caído durante Fase 2.1, el fallback a DB tiene la race condition ya documentada en upload.py. El flujo de Fase 2 necesita preservar el doble-check (SELECT + catch IntegrityError). |
| **Dataset sintético para 2.7.1** | 40 comprobantes etiquetados (20 únicos + 10 duplicados + 10 sospechosos) requieren fixtures con variaciones controladas. Los "sospechosos" son los más difíciles de generar: deben estar en el rango 0.75-0.90 del scoring, lo cual depende de los valores exactos de los campos. |

---

## 5. Orden recomendado de implementación

Dado el análisis de dependencias y riesgos, el orden lógico es:

### Bloque A — Fundamentos (prerequisitos de todo)
```
A1: Decisión sobre texto_extraido (¿persiste en upload.py o S_texto fallback?)
A2: 2.6.1 → state_machine.py (transitions, guard clauses, errores)
A3: 2.6.2 → Tests de state_machine (cada transición válida e inválida)
```

### Bloque B — Detección sincrona (capas en orden de cascada)
```
B1: 2.1.1 + 2.1.2 + 2.1.3 → Ampliar cache_service.py (check_hash + set_hash)
B2: Tests unitarios de check_hash/set_hash (monkeypatch Redis)
B3: 2.2.2 → Migración Alembic: índice compuesto (referencia, monto, fecha_deposito)
B4: 2.2.1 + 2.2.3 → Lógica de Capa 2 en duplicate_service.py
B5: 2.3.1-2.3.6 → Capa 3: scoring ponderado completo en duplicate_service.py
B6: Tests unitarios de compute_score (parametrizados con tablas de casos)
B7: Integrar las 3 capas en upload.py (reemplazar _find_existing_by_hash)
B8: Tests de integración E2E del pipeline completo (actualizar test_upload_endpoint.py)
```

### Bloque C — Endpoints nuevos
```
C1: 2.5.1 → POST /validate/{id} + schema + tests
C2: 2.5.2 → GET /report + schema + tests
```

### Bloque D — Celery (último: depende de todo lo anterior)
```
D1: 2.4.5 → docker-compose.yml (servicio celery-worker)
D2: 2.4.1 → tasks/process_slip.py (task que envuelve el pipeline completo)
D3: 2.4.2 → POST /upload-slip/async
D4: 2.4.3 → GET /status/{task_id}
D5: Tests de las tareas Celery (con task_always_eager)
D6: 2.4.4 → documentar comando del worker
```

### Bloque E — Criterios de aceptación
```
E1: Dataset sintético para 2.7.1 (40 comprobantes con variaciones controladas)
E2: Smoke test 2.7.2 (hash exacto <100ms contra Redis real)
E3: Smoke test 2.7.3 (flujo síncrono ≤5s)
E4: Smoke test 2.7.4 (tarea Celery <30s)
E5: Tests 2.7.5 (validate/{id} 100% casos)
```

---

## 6. Archivos afectados (resumen para el orquestador)

| Archivo | Cambio |
|---------|--------|
| `api/services/cache_service.py` | Agregar `check_hash`, `set_hash`, opcionalmente `get_task_status` |
| `api/services/duplicate_service.py` | CREAR — Capas 2 y 3, `compute_score`, clasificador |
| `api/services/state_machine.py` | CREAR — transiciones, guards, eventos |
| `api/tasks/process_slip.py` | CREAR — tarea Celery con pipeline completo |
| `api/routers/upload.py` | Modificar — integrar 3 capas, state machine, Redis set post-commit |
| `api/routers/validate.py` | CREAR — `POST /validate/{id}` |
| `api/routers/report.py` | CREAR — `GET /report` |
| `api/routers/status.py` | CREAR — `GET /status/{task_id}` |
| `api/routers/async_upload.py` | CREAR (o agregar a upload.py) — `POST /upload-slip/async` |
| `api/schemas/validacion.py` | CREAR — schemas para respuestas de validación |
| `api/schemas/report.py` | CREAR — schema de reporte |
| `api/main.py` | Registrar routers nuevos |
| `api/alembic/versions/` | Nueva migración: índice compuesto + (posiblemente) `id_comprobante_original` en Validacion |
| `infra/docker-compose.yml` | Agregar servicio `celery-worker` |
| `api/tests/test_cache_service.py` | Agregar tests de `check_hash`/`set_hash` |
| `api/tests/test_duplicate_service.py` | CREAR — tests unitarios de scoring |
| `api/tests/test_state_machine.py` | CREAR — tests de cada transición |
| `api/tests/test_upload_endpoint.py` | Actualizar — casos con 3 capas activas |
| `api/tests/test_validate_endpoint.py` | CREAR |
| `api/tests/test_report_endpoint.py` | CREAR |
| `api/tests/test_process_slip_task.py` | CREAR — Celery con task_always_eager |

---

## 7. Decisiones previas que el orquestador debe plantear al usuario

Antes de proponer el plan concreto, hay **2 decisiones bloqueantes**:

### Decisión pendiente 1: `texto_extraido`
**¿Persiste en Fase 2 o no?**
- **Opción A** — Persistir desde ahora: cambiar `upload.py` línea 204 de `texto_extraido=None` a `texto_extraido=crudos.get("content")` (el LLM devuelve el texto raw en `content`). Habilita `S_texto` completo (peso 0.30 real). Requiere entender qué devuelve exactamente el LLM.
- **Opción B** — No persistir: `S_texto` se computa a 0.0 cuando `texto_extraido` is NULL, y los pesos de los otros componentes se renormalizan dinámicamente. El umbral de 0.90 sigue siendo alcanzable solo si `S_ref + S_monto + S_fecha` renormalizados superan el umbral. Matemáticamente más complejo.
- **Opción C** — No persistir pero usar `referencia + numero_operacion` como proxy de texto para TF-IDF. Simple, pero desvía del plan.

### Decisión pendiente 2: `id_comprobante_original` en Validacion
**¿Agregar FK al comprobante original en Fase 2 o diferir a Fase 4?**
- **Agregar ahora**: una migración pequeña, pero la relación entre Validacion y "el comprobante del que es duplicado" es información que el sistema debería capturar en el momento de la detección (antes de poder relacionarlos después es mucho más difícil).
- **Diferir a Fase 4**: menos scope en Fase 2, pero la vista side-by-side de Fase 4 necesitará reconstruir esta relación de otra forma.

---

## Estado: Ready for Proposal

Las 2 decisiones de §7 son desbloqueantes. Una vez resueltas, el plan de implementación puede ser directo siguiendo el orden A→B→C→D→E de §5.
