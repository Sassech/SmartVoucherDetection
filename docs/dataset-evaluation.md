# Dataset Evaluation Report

**Proyecto:** SmartVoucherDetection
**Fase:** 5.0 — Dataset Strategy
**Fecha de generacion:** 2026-10-26
**Autor:** Saul Alonso Serrano

---

## 1. SROIE — Evaluacion del pipeline OCR

Evaluacion del pipeline OCR sobre el dataset publico [SROIE](https://rrc.cvc.uab.es/?ch=13) (Scanned Receipts OCR and Information Extraction, ICDAR 2019). Mide la capacidad del sistema para extraer `monto` y `fecha` de tickets de compra en ingles, un dominio externo al entrenamiento/validacion interna (bancario-mx).

**Configuracion de la corrida (2026-10-26):**
- Split: `test` del mirror Kaggle "SROIE datasetv2" (Urbikn) — **347 recibos** con imagen + ground-truth de entidades
- Ground-truth convertido de `entities/*.json` a formato key:value (`DATE:` / `TOTAL:`) — ver 4.4
- Modelo OCR: gemma-4-E2B-it-qat via llama-server (puerto 9931, `-np 2`, Vulkan)
- Concurrencia: 2 requests simultaneos

### 1.1 Metricas por campo

| Campo | Precision | Recall | F1 | TP | FP | FN |
|-------|-----------|--------|----|----|----|-----|
| `monto` | 0.7088 | 0.9797 | **0.8225** | 241 | 99 | 5 |
| `fecha` | 0.8892 | 0.9871 | **0.9356** | 305 | 38 | 4 |

**Criterio de aceptacion:** F1[monto] >= 0.80

**Resultado:** **PASS** (F1[monto]=0.8225 >= 0.80)

> Contraste con bancario-mx (F1 scoring=0.9855 sobre dataset parcialmente
> sintetico): en el benchmark externo SROIE el F1 de monto baja a 0.8225.
> La precision de monto (0.7088) es el punto debil: el modelo casi siempre
> extrae un monto (recall 0.9797) pero en ~29% de los casos lee mal el valor
> — tipicamente totales pequeños en tipografia densa (ej. GT 38.90 -> pred
> 50.00, GT 7.30 -> pred 10.89). La fecha es mucho mas robusta (0.9356).
> Esto valida la advertencia del guion: el F1 del dataset propio no
> generaliza sin validacion externa.

### 1.2 Tolerancias aplicadas

- `monto`: diferencia absoluta <= $0.01 (centavos)
- `fecha`: diferencia <= 1 dia (formatos ambiguos DD/MM vs MM/DD)

### 1.3 Distribucion de errores SROIE

| Clase de error | Frecuencia | Ejemplo |
|----------------|------------|---------|
| Monto mal leido (FP de `match_total`) | 99 | GT `38.90` -> pred `50.00` (X51008099086) |
| Fecha mal leida (FP de `match_date`) | 38 | GT `2018-02-09` -> pred `2018-02-02` (X51005200931) |
| Monto sin extraccion (pred=None, cuenta FN) | 7 (2 sin GT) | — |
| Fecha sin extraccion (pred=None, cuenta FN) | 4 | — |
| OCR no retorno resultado (error de servidor) | 1 | X51006619694: `503 no devolvio JSON valido` |

> **Nota de alcance**: el ground-truth de SROIE cubre TOTAL y DATE (task 2/3);
> los otros cinco campos del schema bancario (referencia, banco, beneficiario,
> etc.) no son evaluables aqui. SROIE es el contraste externo para `monto` y
> `fecha`, no una validacion completa del schema.

---

## 2. Bancario-MX — Evaluacion del motor de duplicados

Evaluacion del motor de deteccion de duplicados de 3 capas sobre el dataset bancario mexicano sintetico. Usa pares controlados con distribucion 30/40/30 (exacto/parcial/negativo).

### 2.1 Metricas por capa

| Capa | Descripcion | Precision | Recall | F1 | TP | FP | FN |
|------|-------------|-----------|--------|----|----|----|-----|
| Capa 1 | Hash SHA-256 (binario exacto) | 1.0 | 0.4286 | 0.60 | 15 | 0 | 20 |
| Capa 2 | Campos (referencia, monto, fecha) | 1.0 | 1.0 | 1.0 | 35 | 0 | 0 |
| Capa 3 | Scoring ponderado (0.35 ref + 0.30 texto + 0.20 monto + 0.15 fecha) | 1.0 | 0.9714 | **0.9855** | 34 | 0 | 1 |

**Criterio de aceptacion:** capa_1.precision == 1.0

**Resultado:** **PASS** (capa_1.precision=1.0; ademas capa_3 F1=0.9855 con FP=0)

> Fuente de verdad: `results/bancario_metrics_v2.json` (corrida 2026-05-21, seed 42).
> La version anterior `results/bancario_metrics.json` tiene el scoring en 0.0 por un
> bug ya corregido — no usarla. Corrida con OCR real sobre pares degradados (v2).

### 2.2 Scores de similitud por tipo de par

| Tipo de par | Min | Max | Media | Mediana |
|-------------|-----|-----|-------|---------|
| `exacto` (copia identica) | 0.7000 | 1.0000 | 0.9800 | 1.0000 |
| `parcial_visual` (JPEG+rotacion) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `negativo` (mismo banco, monto distinto) | 0.4042 | 0.7582 | 0.5336 | 0.5072 |

### 2.3 Matriz de confusion 3x3

Prediccion (scoring) vs clasificacion esperada.

|  | Predicho: `duplicado` | Predicho: `sospechoso` | Predicho: `valido` |
|--|----------------------|------------------------|---------------------|
| Esperado: `duplicado_exacto` | 14 | 0 | 1 |
| Esperado: `duplicado_parcial` | 20 | 0 | 0 |
| Esperado: `no_duplicado` | 0 | 1 | 14 |

La unica confusion de la capa 3: un par exacto clasificado `valido`
(score 0.70 — el minimo del grupo `exacto`; sin texto OCR renormalizado no
supera el umbral de duplicado 0.90). Los pares `duplicado_parcial` pasan
todos por Capa 2 (campos identicos) antes de llegar al scoring.

### 2.4 Metricas por calidad de imagen

| Calidad | Pares | capa_1 precision | Scoring media |
|---------|-------|------------------|---------------|
| `alta` | 50 | 1.0 | 0.8541 |
| `media` | — | — | — |
| `baja` | — | — | — |

> Los pares de la corrida v2 se generaron todos con calidad `alta`.

---

## 3. Analisis de errores

### 3.1 Falsos positivos de Capa 1

**Ninguno** (FP=0). El hash SHA-256 no produjo colisiones — comportamiento
esperado; el problema de la capa 1 es su recall bajo (0.4286) por diseño,
no su precision.

### 3.2 Falsos negativos de Capa 2

**Ninguno** (FN=0, FP=0, F1=1.0). Todos los pares duplicados con campos
identicos fueron detectados.

### 3.3 Observaciones sobre Layer 3 (scoring)

El unico FN de la capa 3 (F1=0.9855): un par `duplicado_exacto` clasificado
`valido` con score 0.70, el minimo de su grupo. Es el limite de la nota
siguiente llevado a datos con OCR real:

> **Nota**: Con imagenes sinteticas sin OCR (`texto_extraido = null`), el score maximo es 0.70
> (S_texto = 0.0, sin renormalizacion de pesos). Esto significa que el threshold de `duplicado`
> (0.90) nunca se alcanza solo con campos estructurados. Layer 3 necesita texto OCR real
> para ser efectivo — su evaluacion completa requiere datos con texto extraido.
> En la corrida v2 (con OCR sobre pares degradados) el score del grupo
> `exacto` sube a media 0.98, confirmando la dependencia del texto extraido.

---

## 4. Reproducibilidad

Todos los comandos se ejecutan desde la raiz del repositorio. No requieren base de datos ni servidor activo.

### 4.1 Generar dataset sintetico

```bash
# Generar 500 vouchers sinteticos (8 bancos, ~62 por banco)
uv run python scripts/augment/generate_synthetic.py \
  --bank all \
  --count 62 \
  --output dataset/bancario-mx/synthetic/ \
  --seed 42
```

### 4.2 Aplicar degradaciones visuales

```bash
# Generar 500 imagenes augmentadas con degradaciones realistas
uv run python scripts/augment/generate_augmented.py \
  --input-dir dataset/bancario-mx/synthetic/images/ \
  --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \
  --output-dir dataset/augmented/ \
  --n 500 \
  --seed 42
```

### 4.3 Generar pares de duplicados

```bash
# Generar 50+ pares con distribucion 30/40/30
uv run python scripts/augment/generate_duplicates.py \
  --images-dir dataset/bancario-mx/synthetic/images/ \
  --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \
  --output-csv dataset/bancario-mx/duplicates/pairs.csv \
  --output-degraded-dir dataset/bancario-mx/duplicates/degraded/ \
  --n 50 \
  --seed 42
```

### 4.4 Evaluar pipeline SROIE

Corrida usada para este reporte (2026-10-26). Todos los comandos desde la
raiz del repositorio.

**Paso 1 — Descargar el dataset.** Mirror Kaggle "SROIE datasetv2"
(Urbikn): https://www.kaggle.com/datasets/urbikn/sroie-datasetv2
Contiene `train/` (626 recibos) y `test/` (347) con `img/`, `box/` y
`entities/`. El ground-truth utilizable para task 2 (KIE) es `entities/`
(JSON por recibo con `date` y `total`). Descomprimir en `dataset/`.

> Alternativa descartada: "ICDAR-2019-SROIE" (zzzDavid) — sus .txt son
> anotaciones de deteccion (task 1: bbox+transcript), NO key:value de
> entidades; no sirven como ground-truth de extraccion. Se borro para
> ahorrar ~1.2 GB.

**Paso 2 — Preparar la estructura que espera el script:**

```bash
mkdir -p dataset/sroie/images dataset/sroie/annotations

# Copiar imagenes del split test
cp "dataset/SROIE2019 - Urban Knupleš/test/img/"*.jpg dataset/sroie/images/

# Convertir entities JSON -> key:value (el parser exige keys exactas
# TOTAL / DATE sin comillas; el JSON crudo no las resuelve)
python3 - << 'EOF'
import json
from pathlib import Path
src = Path("dataset/SROIE2019 - Urban Knupleš/test")
out = Path("dataset/sroie/annotations")
for txt in sorted(src.glob("entities/*.txt")):
    d = json.loads(txt.read_text(encoding="utf-8", errors="replace"))
    if not d.get("date") or not d.get("total"):
        continue
    (out / f"{txt.stem}.txt").write_text(
        f"DATE: {d['date']}\nTOTAL: {d['total']}\n", encoding="utf-8")
EOF
```

**Paso 3 — Levantar llama-server** (script del repo `llama.cpp/`):

```bash
cd llama.cpp && ./gemma-4-E2B-it-qat.sh
```

> IMPORTANTE: el script quedo con `-np 2` (paralelismo validado para
> 4 GB de VRAM). La corrida original con `-np 8` crasheo con
> `vk::DeviceLostError` al servir 4 requests simultaneos de eval.

**Paso 4 — Correr el pipeline** (el servidor escucha en 9931; el valor
por defecto de `.env` es 8080, hay que overridear):

```bash
LLAMA_SERVER_URL=http://localhost:9931 uv run python \
  scripts/eval/run_pipeline_sroie.py \
  --images-dir dataset/sroie/images/ \
  --annotations-dir dataset/sroie/annotations/ \
  --output-csv results/sroie_results.csv \
  --concurrency 2
```

- `--concurrency 2` coincide con `-np 2` del servidor.
- El CSV es checkpoint: filas ya presentes se saltan; si una corrida se
  interrumpe, se puede relanzar igual y continua donde quedo (borrar solo
  las filas con la columna `error` no vacia antes de relanzar).

**Paso 5 — Calcular metricas:**

```bash
uv run python scripts/eval/metrics_sroie.py \
  --input-csv results/sroie_results.csv \
  --output-json results/sroie_metrics.json
```

Salida esperada (2026-10-26): monto F1=0.8225, fecha F1=0.9356,
criterio F1[monto]>=0.80 -> PASS.

### 4.5 Evaluar motor de duplicados bancario-mx

```bash
# No requiere DB ni servidor — evaluacion standalone
uv run python scripts/eval/eval_duplicates_bancario.py \
  --pairs-csv dataset/bancario-mx/duplicates/pairs.csv \
  --images-dir dataset/bancario-mx/synthetic/images/ \
  --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \
  --degraded-dir dataset/bancario-mx/duplicates/degraded/ \
  --output-json results/bancario_metrics_v2.json
```

---

## 5. Datos del dataset

| Metrica | Valor |
|---------|-------|
| Total imagenes reales (raw) | 30 |
| Total imagenes sinteticas | 500 |
| Total imagenes augmentadas | 500 |
| Total pares de duplicados | 50 |
| Bancos cubiertos | 8 (BBVA, Banorte, Santander, Banamex, Mercado Pago, OXXO, BanCoppel, Banco Azteca) |
| Schema ground-truth | v2.0 |
| Tipos de comprobante | 7 (spei_recibido, spei_enviado, deposito_efectivo, transferencia_interna, pago_servicio, retiro_cajero, deposito_cheque) |
| Formatos de origen | 4 (screenshot_movil, pdf_digital, ticket_impreso, email_html) |
| Seed determinista | 42 |

---

## Licencia

Dataset bancario-mx: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Las imagenes sinteticas contienen datos ficticios generados con Faker. No contienen datos personales reales.
