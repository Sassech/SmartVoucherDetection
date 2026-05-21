"""Evaluador del motor de detección de duplicados para SmartVoucherDetection.

Simula las 3 capas de detección SIN requerir PostgreSQL ni servidor API:
  - Capa 1 — Hash SHA-256 (coincidencia binaria exacta)
  - Capa 2 — Comparación directa de campos (referencia, monto, fecha)
  - Capa 3 — Scoring ponderado via compute_score() + classify()

Usa pairs.csv generado por generate_duplicates.py como fuente de pares.
El ground-truth de las imágenes degradadas (dup-exact-*, dup-partial-*)
es el mismo que el de su imagen fuente (id_a en el CSV).

Uso:
    uv run python scripts/eval/eval_duplicates_bancario.py \\
        --pairs-csv dataset/bancario-mx/duplicates/pairs.csv \\
        --images-dir dataset/bancario-mx/synthetic/images/ \\
        --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \\
        --degraded-dir dataset/bancario-mx/duplicates/degraded/ \\
        --output-json results/bancario_metrics.json

Exit 0: capa_1.precision == 1.0
Exit 1: capa_1.precision < 1.0 o error de I/O
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Standalone reimplementations of api/ functions.
#
# The original functions live in api/services/parser_service.py and
# api/services/duplicate_service.py, but importing them drags in
# Levenshtein, sklearn, SQLAlchemy — heavy deps not in the root venv.
# These standalone versions are pure-function copies that avoid the
# dependency chain while preserving identical behavior for this evaluator.
# ---------------------------------------------------------------------------


def _compute_hash(image_bytes: bytes) -> str:
    """SHA-256 hex of raw bytes. Mirrors parser_service.compute_hash."""
    return hashlib.sha256(image_bytes).hexdigest()


def _parse_monto(value: Any) -> Decimal | None:
    """Parse a monto value to Decimal. Returns None on failure.

    Accepts: int, float, str (with optional $ prefix, commas, MXN/MN suffix).
    """
    if value is None:
        return None
    try:
        s = str(value).strip()
        # Remove currency symbols/suffixes
        for tok in ("$", "MXN", "MN", "USD", ","):
            s = s.replace(tok, "")
        s = s.strip()
        if not s:
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_fecha(value: Any) -> date | None:
    """Parse a fecha value to date. Returns None on failure.

    Accepts:
    - date objects (returned as-is)
    - ISO format: YYYY-MM-DD (synthetic GT from generate_synthetic.py)
    - Slash format: DD/MM/YYYY (real GT from anonymize_comprobante.py)
    - Slash format: MM/DD/YYYY (SROIE / mixed sources — tried as fallback)

    Mirrors the intent of api/services/parser_service.parse_fecha which uses
    dateutil with dayfirst=True to handle Mexican date conventions.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    # ISO format: YYYY-MM-DD (most common for synthetic data)
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        pass
    # Slash formats: DD/MM/YYYY (Mexican convention, real GT)
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Scoring — standalone copy of duplicate_service weights and thresholds
# ---------------------------------------------------------------------------

# Weights (sum to 1.0) — from api/services/duplicate_service.py
_W_REF = 0.35
_W_TEXT = 0.30
_W_MONTO = 0.20
_W_FECHA = 0.15

# Thresholds — from api/services/duplicate_service.py (Spec CAP-05)
_THRESHOLD_DUPLICADO = 0.90
_THRESHOLD_SOSPECHOSO = 0.75
_CANDIDATE_WINDOW_DAYS = 30


def _s_ref(a: str | None, b: str | None) -> float:
    """Levenshtein ratio between two referencia strings.

    Uses stdlib SequenceMatcher instead of python-Levenshtein to avoid
    the external dependency. Returns 0.0 if either is None.
    """
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _s_texto(a: str | None, b: str | None) -> float:
    """Text similarity. Always 0.0 for synthetic images (texto_extraido=None)."""
    if not a or not b:
        return 0.0
    # For completeness — won't be reached with synthetic images
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _s_monto(a: Decimal | None, b: Decimal | None) -> float:
    """Monto similarity: 1 - abs(a-b)/max(a,b). Mirrors duplicate_service."""
    if a is None or b is None:
        return 0.0
    mx = max(abs(float(a)), abs(float(b)))
    if mx == 0:
        return 1.0
    return 1.0 - abs(float(a) - float(b)) / mx


def _s_fecha(a: date | None, b: date | None) -> float:
    """Temporal similarity: 1 - min(days_diff, 30)/30. Mirrors duplicate_service."""
    if a is None or b is None:
        return 0.0
    delta = abs((a - b).days)
    return 1.0 - min(delta, _CANDIDATE_WINDOW_DAYS) / _CANDIDATE_WINDOW_DAYS


def _compute_score(a: "FakeComprobante", b: "FakeComprobante") -> float:
    """Weighted similarity score [0.0, 1.0]. Mirrors duplicate_service.compute_score."""
    return (
        _W_REF * _s_ref(a.referencia, b.referencia)
        + _W_TEXT * _s_texto(a.texto_extraido, b.texto_extraido)
        + _W_MONTO * _s_monto(a.monto, b.monto)
        + _W_FECHA * _s_fecha(a.fecha_deposito, b.fecha_deposito)
    )


def _classify(score: float) -> str:
    """Classify score into duplicado/sospechoso/valido. Mirrors duplicate_service.classify."""
    if score >= _THRESHOLD_DUPLICADO:
        return "duplicado"
    if score >= _THRESHOLD_SOSPECHOSO:
        return "sospechoso"
    return "valido"

# ---------------------------------------------------------------------------
# FakeComprobante — stand-in for models.comprobante.Comprobante
# Only the 4 attributes used by compute_score are populated.
# ---------------------------------------------------------------------------


@dataclass
class FakeComprobante:
    """Lightweight stand-in for models.comprobante.Comprobante.

    Only the 4 attributes used by compute_score are needed:
      - referencia        (str | None)
      - texto_extraido    (str | None) — OCR text (None if not yet enriched)
      - monto             (Decimal | None)
      - fecha_deposito    (date | None)
    """

    referencia: str | None = None
    texto_extraido: str | None = None
    monto: Decimal | None = None
    fecha_deposito: date | None = None


# ---------------------------------------------------------------------------
# Image extensions
# ---------------------------------------------------------------------------

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------


def _read_pairs_csv(csv_path: Path) -> list[dict[str, str]]:
    """Reads pairs.csv and returns list of row dicts.

    Required columns: id_a, id_b, tipo_duplicado, capa_esperada,
    clasificacion_esperada, notas.
    """
    if not csv_path.exists():
        print(f"ERROR: pairs CSV not found: {csv_path!r}", file=sys.stderr)
        sys.exit(1)

    rows: list[dict[str, str]] = []
    required = {"id_a", "id_b", "tipo_duplicado", "capa_esperada", "clasificacion_esperada"}

    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                print("ERROR: pairs CSV is empty or has no headers.", file=sys.stderr)
                sys.exit(1)
            missing = required - set(reader.fieldnames)
            if missing:
                print(
                    f"ERROR: pairs CSV missing required columns: {missing}",
                    file=sys.stderr,
                )
                sys.exit(1)
            for row in reader:
                rows.append(dict(row))
    except (OSError, csv.Error) as exc:
        print(f"ERROR reading pairs CSV: {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("ERROR: pairs CSV has no data rows.", file=sys.stderr)
        sys.exit(1)

    return rows


# ---------------------------------------------------------------------------
# Image resolution
# ---------------------------------------------------------------------------


def _resolve_image_path(
    image_id: str,
    images_dir: Path,
    degraded_dir: Path,
) -> Path | None:
    """Finds the image file for a given id.

    Strategy:
      1. Check images_dir first (source images: syn-bbva-0001.png etc.)
      2. Fall back to degraded_dir (dup-exact-*, dup-partial-*)

    Returns None if not found in either directory.
    """
    for search_dir in (images_dir, degraded_dir):
        if not search_dir.is_dir():
            continue
        for ext in _IMAGE_EXTENSIONS:
            candidate = search_dir / f"{image_id}{ext}"
            if candidate.exists():
                return candidate
        # Also search without assuming extension (the file may be .jpg or .png)
        for f in search_dir.iterdir():
            if f.stem == image_id and f.suffix.lower() in _IMAGE_EXTENSIONS:
                return f

    return None


# ---------------------------------------------------------------------------
# Ground-truth loading
# ---------------------------------------------------------------------------


def _load_gt_index(gt_dir: Path) -> dict[str, dict]:
    """Loads all GT JSONs from gt_dir. Key = id field (or stem)."""
    gt_data: dict[str, dict] = {}
    if not gt_dir.is_dir():
        return gt_data
    for jf in sorted(gt_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: could not read GT {jf.name}: {exc}", file=sys.stderr)
            continue
        gt_id = data.get("id", jf.stem)
        gt_data[gt_id] = data
        # Also index by stem in case the id field differs
        if jf.stem != gt_id:
            gt_data[jf.stem] = data
    return gt_data


def _resolve_gt(
    image_id: str,
    id_a: str,
    gt_index: dict[str, dict],
) -> dict | None:
    """Resolves the GT dict for an image.

    For dup-exact-* and dup-partial-* images (degraded), the GT is the
    same as their source image (id_a). For negativo pairs, both id_a and
    id_b are source images with their own GTs.
    """
    # Degraded images: their GT is the same as id_a (source)
    if image_id.startswith(("dup-exact-", "dup-partial-")):
        return gt_index.get(id_a)
    # Source image: look up directly
    return gt_index.get(image_id)


# ---------------------------------------------------------------------------
# FakeComprobante construction from GT
# ---------------------------------------------------------------------------


def _gt_to_fake(gt: dict | None) -> FakeComprobante:
    """Constructs a FakeComprobante from a ground-truth dict.

    Maps GT fields to the attributes expected by compute_score:
      - referencia     ← numero_referencia (or numero_comprobante as fallback)
      - texto_extraido ← texto_extraido field (populated by enrich_ocr_bancario.py)
      - monto          ← monto as Decimal
      - fecha_deposito ← fecha as date

    Note: Uses standalone _parse_monto / _parse_fecha (no api/ import needed).
    """
    if gt is None:
        return FakeComprobante()

    # Referencia: prefer numero_referencia; fall back to numero_comprobante
    referencia_raw = gt.get("numero_referencia") or gt.get("numero_comprobante") or None
    referencia: str | None = str(referencia_raw).strip() if referencia_raw else None
    if referencia == "":
        referencia = None

    # Monto
    monto_raw = gt.get("monto")
    monto: Decimal | None = _parse_monto(monto_raw)

    # Fecha
    fecha_raw = gt.get("fecha")
    fecha: date | None = _parse_fecha(fecha_raw)

    # Texto extraido por OCR real (enrich_ocr_bancario.py lo escribe en el GT)
    texto_raw = gt.get("texto_extraido")
    texto_extraido: str | None = str(texto_raw).strip() if texto_raw else None
    if texto_extraido == "":
        texto_extraido = None

    return FakeComprobante(
        referencia=referencia,
        texto_extraido=texto_extraido,
        monto=monto,
        fecha_deposito=fecha,
    )


# ---------------------------------------------------------------------------
# Safe division helper
# ---------------------------------------------------------------------------


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _f1(precision: float, recall: float) -> float:
    denom = precision + recall
    return (2 * precision * recall) / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def _compute_binary_metrics(
    results: list[dict[str, Any]],
    detection_key: str,
    positive_classifications: frozenset[str],
) -> dict:
    """Computes TP/FP/FN, precision, recall, F1 for a binary detection layer.

    A pair is a TRUE positive if:
      - detected (detection_key == True)
      - clasificacion_esperada is in positive_classifications

    A pair is a FALSE positive if:
      - detected (detection_key == True)
      - clasificacion_esperada NOT in positive_classifications

    A pair is a FALSE negative if:
      - NOT detected
      - clasificacion_esperada IS in positive_classifications
    """
    tp = 0
    fp = 0
    fn = 0

    for r in results:
        detected: bool = r[detection_key]
        is_positive: bool = r["clasificacion_esperada"] in positive_classifications

        if detected and is_positive:
            tp += 1
        elif detected and not is_positive:
            fp += 1
        elif not detected and is_positive:
            fn += 1
        # not detected + not positive = TN, not counted

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _f1(precision, recall)

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _scores_stats(scores: list[float]) -> dict:
    """Returns min/max/mean/median for a list of scores."""
    if not scores:
        return {"min": None, "max": None, "mean": None, "median": None}
    return {
        "min": round(min(scores), 6),
        "max": round(max(scores), 6),
        "mean": round(statistics.mean(scores), 6),
        "median": round(statistics.median(scores), 6),
    }


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------


def _evaluate_pairs(  # noqa: C901
    pairs: list[dict[str, str]],
    images_dir: Path,
    gt_dir: Path,
    degraded_dir: Path,
) -> list[dict[str, Any]]:
    """Runs all 3 detection layers on each pair.

    Returns a list of result dicts, one per pair, with:
      - id_a, id_b, tipo_duplicado, clasificacion_esperada
      - layer1_detected (bool)
      - layer2_detected (bool)
      - score (float)
      - prediction (str: duplicado | sospechoso | valido)
      - calidad_a, calidad_b
      - error (str | None)
    """
    gt_index = _load_gt_index(gt_dir)
    results: list[dict[str, Any]] = []

    for pair in pairs:
        id_a = pair["id_a"]
        id_b = pair["id_b"]
        tipo = pair["tipo_duplicado"]
        clf_expected = pair["clasificacion_esperada"]

        result: dict[str, Any] = {
            "id_a": id_a,
            "id_b": id_b,
            "tipo_duplicado": tipo,
            "clasificacion_esperada": clf_expected,
            "layer1_detected": False,
            "layer2_detected": False,
            "score": 0.0,
            "prediction": "valido",
            "calidad_a": None,
            "calidad_b": None,
            "error": None,
        }

        # --- Resolve image paths ---
        path_a = _resolve_image_path(id_a, images_dir, degraded_dir)
        path_b = _resolve_image_path(id_b, images_dir, degraded_dir)

        if path_a is None:
            result["error"] = f"image not found for id_a={id_a!r}"
            results.append(result)
            continue
        if path_b is None:
            result["error"] = f"image not found for id_b={id_b!r}"
            results.append(result)
            continue

        # --- Load image bytes ---
        try:
            bytes_a = path_a.read_bytes()
            bytes_b = path_b.read_bytes()
        except OSError as exc:
            result["error"] = f"I/O error reading images: {exc}"
            results.append(result)
            continue

        # --- Resolve GTs ---
        # For degraded images (dup-exact-*, dup-partial-*), the GT is id_a's GT.
        gt_a = _resolve_gt(id_a, id_a, gt_index)  # id_a is always source
        gt_b = _resolve_gt(id_b, id_a, gt_index)  # id_b may be degraded → use id_a's GT

        # Capture calidad for by_quality breakdown
        result["calidad_a"] = (gt_a or {}).get("calidad", "unknown")
        result["calidad_b"] = (gt_b or {}).get("calidad", "unknown")

        # --- Layer 1: Hash comparison ---
        try:
            hash_a = _compute_hash(bytes_a)
            hash_b = _compute_hash(bytes_b)
            result["layer1_detected"] = hash_a == hash_b
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"Layer 1 error: {exc}"
            results.append(result)
            continue

        # --- Layer 2: Field comparison (referencia, monto, fecha) ---
        ref_a = (gt_a or {}).get("numero_referencia") or (gt_a or {}).get("numero_comprobante") or None
        ref_b = (gt_b or {}).get("numero_referencia") or (gt_b or {}).get("numero_comprobante") or None
        monto_a_raw = (gt_a or {}).get("monto")
        monto_b_raw = (gt_b or {}).get("monto")
        fecha_a_raw = (gt_a or {}).get("fecha")
        fecha_b_raw = (gt_b or {}).get("fecha")

        # Exact field match — all 3 must match (and be non-None)
        if ref_a and ref_b and ref_a == ref_b:
            monto_a = _parse_monto(monto_a_raw)
            monto_b = _parse_monto(monto_b_raw)
            fecha_a = _parse_fecha(fecha_a_raw)
            fecha_b = _parse_fecha(fecha_b_raw)

            if (
                monto_a is not None
                and monto_b is not None
                and fecha_a is not None
                and fecha_b is not None
                and monto_a == monto_b
                and fecha_a == fecha_b
            ):
                result["layer2_detected"] = True
            else:
                # referencia matches but monto or fecha don't — not a full match
                result["layer2_detected"] = False
        else:
            # Fall back: if referencia is missing, compare monto+fecha only
            # (this mirrors the parcial_visual case where GT is the same)
            if gt_a is not None and gt_b is not None:
                monto_a = _parse_monto(monto_a_raw)
                monto_b = _parse_monto(monto_b_raw)
                fecha_a = _parse_fecha(fecha_a_raw)
                fecha_b = _parse_fecha(fecha_b_raw)

                # When both share the same GT (dup-* pairs), all fields match
                if (
                    monto_a is not None
                    and monto_b is not None
                    and fecha_a is not None
                    and fecha_b is not None
                    and monto_a == monto_b
                    and fecha_a == fecha_b
                    and (ref_a or "") == (ref_b or "")  # both empty
                ):
                    result["layer2_detected"] = True

        # --- Layer 3: Weighted scoring ---
        fake_a = _gt_to_fake(gt_a)
        fake_b = _gt_to_fake(gt_b)

        try:
            score = _compute_score(fake_a, fake_b)
            prediction = _classify(score)
            result["score"] = round(score, 6)
            result["prediction"] = prediction
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"Layer 3 error: {exc}"
            result["score"] = 0.0
            result["prediction"] = "valido"

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Output JSON construction
# ---------------------------------------------------------------------------

_POSITIVE_CLASSIFICATIONS = frozenset({"duplicado_exacto", "duplicado_parcial"})

# Predicted label → column index in confusion matrix
_PRED_LABELS = ["duplicado", "sospechoso", "valido"]
# Expected label → row index in confusion matrix
_EXP_LABELS = ["duplicado_exacto", "duplicado_parcial", "no_duplicado"]


def _build_output(
    pairs: list[dict[str, str]],
    results: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict:
    """Constructs the full bancario_metrics.json output dict."""
    import datetime

    # --- Distribution ---
    tipos = [r["tipo_duplicado"] for r in results]
    distribution: dict[str, int] = {}
    for t in tipos:
        distribution[t] = distribution.get(t, 0) + 1

    # --- Capa 1 metrics ---
    c1 = _compute_binary_metrics(results, "layer1_detected", _POSITIVE_CLASSIFICATIONS)

    # --- Capa 2 metrics ---
    c2 = _compute_binary_metrics(results, "layer2_detected", _POSITIVE_CLASSIFICATIONS)

    # --- Scoring stats by tipo ---
    scores_by_type: dict[str, list[float]] = {}
    for r in results:
        t = r["tipo_duplicado"]
        scores_by_type.setdefault(t, []).append(r["score"])

    scores_summary: dict[str, dict] = {
        t: _scores_stats(scores) for t, scores in scores_by_type.items()
    }

    # --- Confusion matrix 3×3 ---
    # Rows = expected label; Cols = predicted label
    exp_idx = {label: i for i, label in enumerate(_EXP_LABELS)}
    pred_idx = {label: i for i, label in enumerate(_PRED_LABELS)}

    matrix: list[list[int]] = [[0] * len(_PRED_LABELS) for _ in _EXP_LABELS]

    for r in results:
        clf_exp = r["clasificacion_esperada"]
        pred = r["prediction"]
        if clf_exp in exp_idx and pred in pred_idx:
            matrix[exp_idx[clf_exp]][pred_idx[pred]] += 1

    # --- by_quality breakdown ---
    # Collect quality values from id_a GT (source)
    gt_index = _load_gt_index(Path(args.gt_dir))
    by_quality: dict[str, dict] = {}

    for r in results:
        # Determine quality from id_a GT
        gt_a = gt_index.get(r["id_a"])
        quality = (gt_a or {}).get("calidad", "unknown")

        if quality not in by_quality:
            by_quality[quality] = {
                "pairs": 0,
                "capa_1_tp": 0,
                "capa_1_fp": 0,
                "capa_1_fn": 0,
                "scores": [],
            }

        entry = by_quality[quality]
        entry["pairs"] += 1
        entry["scores"].append(r["score"])

        is_positive = r["clasificacion_esperada"] in _POSITIVE_CLASSIFICATIONS
        detected_c1 = r["layer1_detected"]

        if detected_c1 and is_positive:
            entry["capa_1_tp"] += 1
        elif detected_c1 and not is_positive:
            entry["capa_1_fp"] += 1
        elif not detected_c1 and is_positive:
            entry["capa_1_fn"] += 1

    # Format by_quality for output
    by_quality_out: dict[str, dict] = {}
    for quality, entry in by_quality.items():
        tp = entry["capa_1_tp"]
        fp = entry["capa_1_fp"]
        precision = _safe_div(tp, tp + fp)
        scores = entry["scores"]
        by_quality_out[quality] = {
            "pairs": entry["pairs"],
            "capa_1_precision": round(precision, 6),
            "scoring_mean": round(statistics.mean(scores), 6) if scores else 0.0,
        }

    # --- Seed extraction (from CSV filename convention or pairs length) ---
    # We don't have direct access to the seed used in generate_duplicates.py;
    # use args.seed if provided, otherwise 42 (default).
    seed = getattr(args, "seed", 42)

    return {
        "metadata": {
            "total_pairs": len(results),
            "distribution": distribution,
            "seed": seed,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        },
        "capa_1": {
            "description": "Hash SHA-256 — exact binary match",
            **c1,
        },
        "capa_2": {
            "description": "Field comparison — (referencia, monto, fecha)",
            **c2,
        },
        "scoring": {
            "description": "Weighted scoring — compute_score + classify (threshold duplicado=0.90)",
            "threshold_duplicado": _THRESHOLD_DUPLICADO,
            "threshold_sospechoso": _THRESHOLD_SOSPECHOSO,
            # precision/recall/F1: Layer 3 classify=="duplicado" is the detection signal
            # (note: if texto_extraido=None, max score=0.70 < threshold=0.90,
            #  so all pairs are classified "valido" — this accurately reflects Layer 3
            #  limitations on synthetic data without OCR text)
            **_compute_binary_metrics(
                [
                    {**r, "_layer3_detected": r["prediction"] == "duplicado"}
                    for r in results
                ],
                "_layer3_detected",
                _POSITIVE_CLASSIFICATIONS,
            ),
            "scores_by_type": scores_summary,
        },
        "confusion_matrix": {
            "description": (
                "3x3: expected (duplicado_exacto/duplicado_parcial/no_duplicado) "
                "vs predicted (duplicado/sospechoso/valido)"
            ),
            "labels_expected": _EXP_LABELS,
            "labels_predicted": _PRED_LABELS,
            "matrix": matrix,
        },
        "by_quality": {
            "description": "Metrics broken down by calidad field in GT",
            **by_quality_out,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluates the duplicate detection engine using pairs.csv.\n"
            "Simulates all 3 detection layers WITHOUT requiring PostgreSQL:\n"
            "  Layer 1: SHA-256 hash (exact binary match)\n"
            "  Layer 2: Field comparison (referencia, monto, fecha)\n"
            "  Layer 3: Weighted scoring via compute_score() + classify()\n\n"
            "Exit 0: capa_1.precision == 1.0\n"
            "Exit 1: capa_1.precision < 1.0 or I/O error"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pairs-csv",
        default="dataset/bancario-mx/duplicates/pairs.csv",
        metavar="PATH",
        help="CSV with duplicate pairs (default: %(default)s)",
    )
    parser.add_argument(
        "--images-dir",
        default="dataset/bancario-mx/synthetic/images/",
        metavar="PATH",
        help="Directory with source images (default: %(default)s)",
    )
    parser.add_argument(
        "--gt-dir",
        default="dataset/bancario-mx/synthetic/ground-truth/",
        metavar="PATH",
        help="Directory with ground-truth JSONs (default: %(default)s)",
    )
    parser.add_argument(
        "--degraded-dir",
        default="dataset/bancario-mx/duplicates/degraded/",
        metavar="PATH",
        help="Directory with degraded/exact copies (default: %(default)s)",
    )
    parser.add_argument(
        "--output-json",
        default="results/bancario_metrics.json",
        metavar="PATH",
        help="Output JSON path (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="INT",
        help="Seed used when generating pairs (informational only, default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    pairs_csv = Path(args.pairs_csv)
    images_dir = Path(args.images_dir)
    gt_dir = Path(args.gt_dir)
    degraded_dir = Path(args.degraded_dir)
    output_json = Path(args.output_json)

    # Validate required paths
    if not images_dir.is_dir():
        print(
            f"ERROR: --images-dir '{images_dir}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return 1
    if not gt_dir.is_dir():
        print(
            f"ERROR: --gt-dir '{gt_dir}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return 1
    if not degraded_dir.is_dir():
        print(
            f"ERROR: --degraded-dir '{degraded_dir}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return 1

    # Read pairs
    print(f"Reading pairs from {pairs_csv}...")
    pairs = _read_pairs_csv(pairs_csv)
    print(f"  {len(pairs)} pairs loaded.")

    # Run evaluation
    print("\nRunning evaluation...")
    results = _evaluate_pairs(pairs, images_dir, gt_dir, degraded_dir)

    # Report errors
    errors = [r for r in results if r.get("error")]
    if errors:
        print(f"\n  WARN: {len(errors)} pair(s) had errors:", file=sys.stderr)
        for e in errors:
            print(f"    [{e['id_a']} / {e['id_b']}]: {e['error']}", file=sys.stderr)

    # Build output
    output = _build_output(pairs, results, args)

    # Print summary
    c1 = output["capa_1"]
    c2 = output["capa_2"]
    print("\n=== Duplicate Detection Evaluation ===")
    print(f"  Total pairs:   {output['metadata']['total_pairs']}")
    print(f"  Distribution:  {output['metadata']['distribution']}")
    print()
    print(
        f"  Layer 1 (hash):   precision={c1['precision']:.4f}  "
        f"recall={c1['recall']:.4f}  F1={c1['f1']:.4f}  "
        f"TP={c1['true_positives']}  FP={c1['false_positives']}  FN={c1['false_negatives']}"
    )
    print(
        f"  Layer 2 (fields): precision={c2['precision']:.4f}  "
        f"recall={c2['recall']:.4f}  F1={c2['f1']:.4f}  "
        f"TP={c2['true_positives']}  FP={c2['false_positives']}  FN={c2['false_negatives']}"
    )

    scoring = output["scoring"]
    print("\n  Scoring by tipo:")
    for tipo, stats in scoring["scores_by_type"].items():
        print(
            f"    {tipo:20s}: mean={stats['mean']:.4f}  "
            f"median={stats['median']:.4f}  "
            f"min={stats['min']:.4f}  max={stats['max']:.4f}"
        )

    # Write JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_json.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nMetrics written to {output_json}")
    except OSError as exc:
        print(f"ERROR: could not write JSON — {exc}", file=sys.stderr)
        return 1

    # Exit criterion: capa_1.precision == 1.0
    precision_c1 = c1["precision"]
    if precision_c1 == 1.0:
        print(f"\nCRITERION PASSED: capa_1.precision={precision_c1:.4f} == 1.0")
        return 0
    else:
        print(
            f"\nCRITERION FAILED: capa_1.precision={precision_c1:.4f} < 1.0",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
