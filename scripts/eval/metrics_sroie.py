"""Calculadora de métricas de evaluación SROIE.

Lee el CSV generado por run_pipeline_sroie.py y calcula precision/recall/F1
para los campos `monto` y `fecha` con la semántica de 3 estados:

    match = True   → TP (predicción correcta)
    match = False  → FP (predicción incorrecta)
    match = (vacío) → None: pred ausente
        - excluido del denominador de precision
        - cuenta como FN en recall (gt existe, pred no llegó)

Criterio de éxito: F1[monto] >= 0.80 → exit 0
                   F1[monto] <  0.80 → exit 1 + mensaje CRITERION FAILED

Uso:
    uv run python scripts/eval/metrics_sroie.py --help
    uv run python scripts/eval/metrics_sroie.py \\
        --input-csv results/sroie_results.csv \\
        --output-json results/sroie_metrics.json

Exit 0: F1[monto] >= 0.80
Exit 1: F1[monto] < 0.80, o CSV no encontrado / malformado
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


def _safe_div(numerator: float, denominator: float) -> float:
    """División segura — devuelve 0.0 si el denominador es cero."""
    return numerator / denominator if denominator > 0 else 0.0


def _f1(precision: float, recall: float) -> float:
    """Media armónica de precision y recall. 0.0 si ambos son cero."""
    denom = precision + recall
    return (2 * precision * recall) / denom if denom > 0 else 0.0


def _compute_metrics(
    match_col: list[str | None],
    gt_col: list[str],
) -> dict:
    """Calcula precision/recall/F1 para una columna de match.

    Semántica de `match_col`:
        "True"   → TP
        "False"  → FP
        ""       → pred=None → excluido de precision, FN si gt existe

    Args:
        match_col: lista de strings ("True", "False", "") — una por imagen
        gt_col: lista de strings gt — usada para determinar si gt existe
                cuando match="". Si gt es vacío, también excluimos del recall.

    Returns:
        dict con precision, recall, f1, support (total de imágenes con gt)
    """
    tp = 0
    fp = 0
    fn = 0  # pred=None pero gt existe
    support = 0  # imágenes donde gt existe (denominador de recall)

    for match_val, gt_val in zip(match_col, gt_col):
        gt_exists = bool(gt_val.strip())
        if gt_exists:
            support += 1

        if match_val == "True":
            tp += 1
        elif match_val == "False":
            fp += 1
        else:
            # match vacío → pred=None
            if gt_exists:
                fn += 1
            # Si gt también está vacío → excluir completamente

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)  # denominator = TP + FN = support de imágenes con pred
    # Nota: recall también puede calcularse como TP/support (equivalente cuando FN = support - TP)
    # Usamos la fórmula TP/(TP+FN) que es más explícita sobre los FN reales
    f1 = _f1(precision, recall)

    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "support": support,
    }


# ---------------------------------------------------------------------------
# Lectura del CSV
# ---------------------------------------------------------------------------


def _read_csv(csv_path: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    """Lee el CSV de SROIE y devuelve las columnas relevantes.

    Returns:
        Tupla (match_total_col, gt_total_col, match_date_col, gt_date_col)
        Cada elemento es una lista de strings (una por fila de datos).

    Raises:
        SystemExit(1): si el archivo no existe o está malformado.
    """
    if not csv_path.exists():
        print(f"ERROR: CSV no encontrado: {csv_path!r}", file=sys.stderr)
        sys.exit(1)

    match_total: list[str] = []
    gt_total: list[str] = []
    match_date: list[str] = []
    gt_date: list[str] = []

    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                print("ERROR: CSV vacío o sin encabezados.", file=sys.stderr)
                sys.exit(1)

            required = {"match_total", "gt_total", "match_date", "gt_date"}
            missing = required - set(reader.fieldnames)
            if missing:
                print(
                    f"ERROR: CSV no tiene las columnas requeridas: {missing}",
                    file=sys.stderr,
                )
                sys.exit(1)

            for row in reader:
                match_total.append(row.get("match_total", "").strip())
                gt_total.append(row.get("gt_total", "").strip())
                match_date.append(row.get("match_date", "").strip())
                gt_date.append(row.get("gt_date", "").strip())

    except (OSError, csv.Error) as exc:
        print(f"ERROR: no se pudo leer el CSV — {exc}", file=sys.stderr)
        sys.exit(1)

    if not match_total:
        print("ERROR: CSV no tiene filas de datos.", file=sys.stderr)
        sys.exit(1)

    return match_total, gt_total, match_date, gt_date


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calcula métricas de evaluación (precision/recall/F1) desde el CSV\n"
            "generado por run_pipeline_sroie.py. Evalúa campos monto y fecha.\n\n"
            "Criterio: F1[monto] >= 0.80 → exit 0 | F1[monto] < 0.80 → exit 1"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-csv",
        default="results/sroie_results.csv",
        metavar="PATH",
        help="CSV de entrada generado por run_pipeline_sroie.py (default: %(default)s)",
    )
    parser.add_argument(
        "--output-json",
        default="results/sroie_metrics.json",
        metavar="PATH",
        help="JSON de salida con métricas (default: %(default)s)",
    )
    parser.add_argument(
        "--tolerance-monto",
        type=float,
        default=0.01,
        metavar="FLOAT",
        help=(
            "Tolerancia para matching de monto (default: %(default)s). "
            "Nota: la tolerancia se aplica en run_pipeline_sroie.py; "
            "este flag es informativo para el JSON de salida."
        ),
    )
    parser.add_argument(
        "--tolerance-fecha",
        type=int,
        default=1,
        metavar="INT",
        help=(
            "Tolerancia para matching de fecha en días (default: %(default)s). "
            "Nota: la tolerancia se aplica en run_pipeline_sroie.py; "
            "este flag es informativo para el JSON de salida."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    input_csv = Path(args.input_csv)
    output_json = Path(args.output_json)

    # Leer datos
    match_total_col, gt_total_col, match_date_col, gt_date_col = _read_csv(input_csv)

    total_rows = len(match_total_col)
    print(f"Leyendo {total_rows} filas de {input_csv}...")

    # Calcular métricas
    monto_metrics = _compute_metrics(match_total_col, gt_total_col)
    fecha_metrics = _compute_metrics(match_date_col, gt_date_col)

    metrics = {
        "monto": monto_metrics,
        "fecha": fecha_metrics,
    }

    # Mostrar resumen
    print("\n=== SROIE Metrics ===")
    for field, m in metrics.items():
        print(
            f"  {field:6s}: precision={m['precision']:.4f}  "
            f"recall={m['recall']:.4f}  F1={m['f1']:.4f}  "
            f"support={m['support']}"
        )

    # Escribir JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_json.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nMétricas guardadas en {output_json}")
    except OSError as exc:
        print(f"ERROR: no se pudo escribir JSON — {exc}", file=sys.stderr)
        return 1

    # Criterio de aceptación: F1[monto] >= 0.80
    f1_monto = monto_metrics["f1"]
    if f1_monto >= 0.80:
        print(f"\nCRITERION PASSED: F1[monto]={f1_monto:.4f} >= 0.80")
        return 0
    else:
        print(
            f"\nCRITERION FAILED: F1[monto]={f1_monto:.4f}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
