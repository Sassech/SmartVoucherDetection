# Dataset Evaluation Report

**Proyecto:** SmartVoucherDetection
**Fase:** 5.0 — Dataset Strategy
**Fecha de generacion:** <!-- FECHA_GENERACION -->
**Autor:** <!-- AUTOR -->

---

## 1. SROIE — Evaluacion del pipeline OCR

Evaluacion del pipeline OCR sobre el dataset publico [SROIE](https://rrc.ccs.uab.es/?ch=13) (Scanned Receipts OCR and Information Extraction). Mide la capacidad del sistema para extraer `monto` y `fecha` de tickets de compra.

### 1.1 Metricas por campo

| Campo | Precision | Recall | F1 | TP | FP | FN |
|-------|-----------|--------|----|----|----|-----|
| `monto` | <!-- P_MONTO --> | <!-- R_MONTO --> | <!-- F1_MONTO --> | <!-- TP_MONTO --> | <!-- FP_MONTO --> | <!-- FN_MONTO --> |
| `fecha` | <!-- P_FECHA --> | <!-- R_FECHA --> | <!-- F1_FECHA --> | <!-- TP_FECHA --> | <!-- FP_FECHA --> | <!-- FN_FECHA --> |

**Criterio de aceptacion:** F1[monto] >= 0.80

**Resultado:** <!-- RESULTADO_SROIE --> <!-- (PASS / FAIL: F1[monto]=X.XX) -->

### 1.2 Tolerancias aplicadas

- `monto`: diferencia absoluta <= $0.01 (centavos)
- `fecha`: diferencia <= 1 dia (formatos ambiguos DD/MM vs MM/DD)

### 1.3 Distribucion de errores SROIE

| Clase de error | Frecuencia | Ejemplo |
|----------------|------------|---------|
| Formato de monto no reconocido | <!-- N_ERR_MONTO_FMT --> | <!-- EJ_MONTO_FMT --> |
| Fecha en formato inesperado | <!-- N_ERR_FECHA_FMT --> | <!-- EJ_FECHA_FMT --> |
| OCR no retorno resultado | <!-- N_ERR_NULL --> | <!-- EJ_NULL --> |
| Monto con decimales truncados | <!-- N_ERR_DEC --> | <!-- EJ_DEC --> |

---

## 2. Bancario-MX — Evaluacion del motor de duplicados

Evaluacion del motor de deteccion de duplicados de 3 capas sobre el dataset bancario mexicano sintetico. Usa pares controlados con distribucion 30/40/30 (exacto/parcial/negativo).

### 2.1 Metricas por capa

| Capa | Descripcion | Precision | Recall | F1 | TP | FP | FN |
|------|-------------|-----------|--------|----|----|----|-----|
| Capa 1 | Hash SHA-256 (binario exacto) | <!-- P_C1 --> | <!-- R_C1 --> | <!-- F1_C1 --> | <!-- TP_C1 --> | <!-- FP_C1 --> | <!-- FN_C1 --> |
| Capa 2 | Campos (referencia, monto, fecha) | <!-- P_C2 --> | <!-- R_C2 --> | <!-- F1_C2 --> | <!-- TP_C2 --> | <!-- FP_C2 --> | <!-- FN_C2 --> |
| Capa 3 | Scoring ponderado (0.35 ref + 0.30 texto + 0.20 monto + 0.15 fecha) | <!-- P_C3 --> | <!-- R_C3 --> | <!-- F1_C3 --> | <!-- TP_C3 --> | <!-- FP_C3 --> | <!-- FN_C3 --> |

**Criterio de aceptacion:** capa_1.precision == 1.0

**Resultado:** <!-- RESULTADO_BANCARIO --> <!-- (PASS / FAIL: capa_1.precision=X.XX) -->

### 2.2 Scores de similitud por tipo de par

| Tipo de par | Min | Max | Media | Mediana |
|-------------|-----|-----|-------|---------|
| `exacto` (copia identica) | <!-- SC_EXACT_MIN --> | <!-- SC_EXACT_MAX --> | <!-- SC_EXACT_MEAN --> | <!-- SC_EXACT_MED --> |
| `parcial_visual` (JPEG+rotacion) | <!-- SC_PART_MIN --> | <!-- SC_PART_MAX --> | <!-- SC_PART_MEAN --> | <!-- SC_PART_MED --> |
| `negativo` (mismo banco, monto distinto) | <!-- SC_NEG_MIN --> | <!-- SC_NEG_MAX --> | <!-- SC_NEG_MEAN --> | <!-- SC_NEG_MED --> |

### 2.3 Matriz de confusion 3x3

Prediccion (scoring) vs clasificacion esperada.

|  | Predicho: `duplicado` | Predicho: `sospechoso` | Predicho: `valido` |
|--|----------------------|------------------------|---------------------|
| Esperado: `duplicado_exacto` | <!-- CM_00 --> | <!-- CM_01 --> | <!-- CM_02 --> |
| Esperado: `duplicado_parcial` | <!-- CM_10 --> | <!-- CM_11 --> | <!-- CM_12 --> |
| Esperado: `no_duplicado` | <!-- CM_20 --> | <!-- CM_21 --> | <!-- CM_22 --> |

### 2.4 Metricas por calidad de imagen

| Calidad | Pares | capa_1 precision | Scoring media |
|---------|-------|------------------|---------------|
| `alta` | <!-- Q_ALTA_N --> | <!-- Q_ALTA_P --> | <!-- Q_ALTA_S --> |
| `media` | <!-- Q_MEDIA_N --> | <!-- Q_MEDIA_P --> | <!-- Q_MEDIA_S --> |
| `baja` | <!-- Q_BAJA_N --> | <!-- Q_BAJA_P --> | <!-- Q_BAJA_S --> |

---

## 3. Analisis de errores

### 3.1 Falsos positivos de Capa 1

<!-- Pares detectados como duplicado_exacto por hash que NO son duplicados reales. -->
<!-- Si capa_1.FP == 0, esta seccion queda vacia — hash SHA-256 no deberia producir colisiones. -->

| id_a | id_b | Tipo real | Hash coincide? | Notas |
|------|------|-----------|----------------|-------|
| <!-- FP1_ID_A --> | <!-- FP1_ID_B --> | <!-- FP1_TIPO --> | Si | <!-- FP1_NOTAS --> |

### 3.2 Falsos negativos de Capa 2

<!-- Pares que SON duplicados pero Capa 2 no detecto (campos no coinciden). -->

| id_a | id_b | Tipo real | ref_match | monto_match | fecha_match | Notas |
|------|------|-----------|-----------|-------------|-------------|-------|
| <!-- FN2_ID_A --> | <!-- FN2_ID_B --> | <!-- FN2_TIPO --> | <!-- FN2_REF --> | <!-- FN2_MONTO --> | <!-- FN2_FECHA --> | <!-- FN2_NOTAS --> |

### 3.3 Observaciones sobre Layer 3 (scoring)

<!-- NOTA_SCORING -->

> **Nota**: Con imagenes sinteticas sin OCR (`texto_extraido = null`), el score maximo es 0.70
> (S_texto = 0.0, sin renormalizacion de pesos). Esto significa que el threshold de `duplicado`
> (0.90) nunca se alcanza solo con campos estructurados. Layer 3 necesita texto OCR real
> para ser efectivo — su evaluacion completa requiere datos con texto extraido.

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

```bash
# Requiere llama-server activo y dataset SROIE descargado
uv run python scripts/eval/run_pipeline_sroie.py \
  --images-dir dataset/sroie/test/img/ \
  --annotations-dir dataset/sroie/test/entities/ \
  --output-csv results/sroie_results.csv \
  --concurrency 4

# Calcular metricas
uv run python scripts/eval/metrics_sroie.py \
  --input-csv results/sroie_results.csv \
  --output-json results/sroie_metrics.json
```

### 4.5 Evaluar motor de duplicados bancario-mx

```bash
# No requiere DB ni servidor — evaluacion standalone
uv run python scripts/eval/eval_duplicates_bancario.py \
  --pairs-csv dataset/bancario-mx/duplicates/pairs.csv \
  --images-dir dataset/bancario-mx/synthetic/images/ \
  --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \
  --degraded-dir dataset/bancario-mx/duplicates/degraded/ \
  --output-json results/bancario_metrics.json
```

---

## 5. Datos del dataset

| Metrica | Valor |
|---------|-------|
| Total imagenes reales (raw) | 30 |
| Total imagenes sinteticas | <!-- N_SYNTH --> |
| Total imagenes augmentadas | <!-- N_AUG --> |
| Total pares de duplicados | <!-- N_PAIRS --> |
| Bancos cubiertos | 8 (BBVA, Banorte, Santander, Banamex, Mercado Pago, OXXO, BanCoppel, Banco Azteca) |
| Schema ground-truth | v2.0 |
| Tipos de comprobante | 7 (spei_recibido, spei_enviado, deposito_efectivo, transferencia_interna, pago_servicio, retiro_cajero, deposito_cheque) |
| Formatos de origen | 4 (screenshot_movil, pdf_digital, ticket_impreso, email_html) |
| Seed determinista | 42 |

---

## Licencia

Dataset bancario-mx: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Las imagenes sinteticas contienen datos ficticios generados con Faker. No contienen datos personales reales.
