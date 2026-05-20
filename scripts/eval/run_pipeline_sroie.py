"""Evaluación batch del pipeline OCR sobre el dataset SROIE.

Flujo por imagen:
    1. Leer anotación ground-truth (TOTAL + DATE) del archivo .txt de SROIE
    2. validate_mime() → preprocess() → to_base64() (image_service)
    3. extract_fields(b64, client=shared_client) con asyncio.Semaphore(--concurrency)
    4. parse_monto() + parse_fecha() (parser_service)
    5. Comparar pred vs gt → match_total / match_date (True|False|None)
    6. Escribir fila al CSV en modo append

Checkpoint: lee CSV existente al inicio para saltar imágenes ya procesadas.
Cliente httpx compartido entre todas las tareas — se cierra al final del batch.

Uso:
    uv run python scripts/eval/run_pipeline_sroie.py --help
    uv run python scripts/eval/run_pipeline_sroie.py \\
        --images-dir dataset/sroie/images/ \\
        --annotations-dir dataset/sroie/annotations/ \\
        --output-csv results/sroie_results.csv \\
        --concurrency 4

Exit 0: OK
Exit 1: sin imágenes encontradas, o llama-server inaccesible
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from decimal import Decimal
from pathlib import Path

# Bootstrap: inserta scripts/ en sys.path para poder importar _shared
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from _shared import get_ocr_client, setup_api_path  # noqa: E402

setup_api_path()

# CSV columns
_CSV_COLUMNS = [
    "image_id",
    "gt_total",
    "gt_date",
    "pred_total",
    "pred_date",
    "match_total",
    "match_date",
    "error",
]


# ---------------------------------------------------------------------------
# Parsing SROIE annotations
# ---------------------------------------------------------------------------


def _parse_sroie_annotation(txt_path: Path) -> tuple[str | None, str | None]:
    """Lee un archivo de anotación SROIE y devuelve (total_str, date_str).

    El formato SROIE es key:value, una por línea. Buscamos TOTAL y DATE
    de forma flexible (case-insensitive, ignora espacios alrededor del ':').

    Returns:
        Tupla (total_str, date_str) — cualquiera puede ser None si no se
        encuentra el campo en el archivo.
    """
    total_str: str | None = None
    date_str: str | None = None

    try:
        lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, None

    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_norm = key.strip().upper()
        value_norm = value.strip()
        if key_norm == "TOTAL":
            total_str = value_norm
        elif key_norm == "DATE":
            date_str = value_norm

    return total_str, date_str


# ---------------------------------------------------------------------------
# Match helpers
# ---------------------------------------------------------------------------


def _match_total(
    pred: Decimal | None,
    gt: Decimal | None,
    tolerance: Decimal = Decimal("0.01"),
) -> bool | None:
    """Compara monto predicho vs ground-truth.

    Returns:
        True  — ambos presentes y |pred - gt| ≤ tolerance
        False — ambos presentes y difieren más de tolerance
        None  — pred es None (excluido de precision, cuenta como FN en recall)
    """
    if pred is None:
        return None
    if gt is None:
        # GT ausente — no podemos evaluar; excluir
        return None
    return abs(pred - gt) <= tolerance


def _match_date(
    pred_date,  # datetime.date | None
    gt_date,    # datetime.date | None
    tolerance_days: int = 1,
) -> bool | None:
    """Compara fecha predicha vs ground-truth.

    Returns:
        True  — ambas presentes y |pred - gt| ≤ tolerance_days
        False — ambas presentes y difieren más de tolerance_days
        None  — pred es None
    """
    if pred_date is None:
        return None
    if gt_date is None:
        return None
    from datetime import timedelta
    delta = abs(pred_date - gt_date)
    return delta <= timedelta(days=tolerance_days)


# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------


async def _check_server_reachable(client) -> bool:
    """Hace un GET a la raíz del server para verificar conectividad.

    Retorna True si el server responde (cualquier status code HTTP),
    False si hay un error de red (connection refused, timeout, etc.).
    """
    import httpx
    try:
        await client.get("/")
        return True
    except httpx.RequestError:
        return False


# ---------------------------------------------------------------------------
# Checkpoint: leer CSV existente
# ---------------------------------------------------------------------------


def _load_processed_ids(csv_path: Path) -> set[str]:
    """Lee el CSV existente y devuelve el conjunto de image_id ya procesados."""
    if not csv_path.exists():
        return set()
    processed: set[str] = set()
    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                img_id = row.get("image_id", "").strip()
                if img_id:
                    processed.add(img_id)
    except (OSError, csv.Error):
        pass
    return processed


# ---------------------------------------------------------------------------
# Core async pipeline per image
# ---------------------------------------------------------------------------


async def _process_image(
    image_path: Path,
    annotations_dir: Path,
    sem: asyncio.Semaphore,
    client,
) -> dict:
    """Ejecuta el pipeline OCR sobre una imagen SROIE.

    Returns:
        dict con las columnas del CSV. 'error' es vacío en éxito.
    """
    image_id = image_path.stem
    row: dict = {
        "image_id": image_id,
        "gt_total": "",
        "gt_date": "",
        "pred_total": "",
        "pred_date": "",
        "match_total": "",
        "match_date": "",
        "error": "",
    }

    # --- Ground truth ---
    ann_path = annotations_dir / (image_id + ".txt")
    gt_total_str, gt_date_str = _parse_sroie_annotation(ann_path)

    from services.parser_service import parse_fecha, parse_monto  # type: ignore[import-untyped]

    gt_total: Decimal | None = parse_monto(gt_total_str)
    gt_date = parse_fecha(gt_date_str)

    row["gt_total"] = str(gt_total) if gt_total is not None else ""
    row["gt_date"] = str(gt_date) if gt_date is not None else ""

    # --- OCR pipeline ---
    try:
        file_bytes = image_path.read_bytes()
    except OSError as exc:
        row["error"] = f"read error: {exc}"
        return row

    try:
        from services.image_service import preprocess, to_base64, validate_mime  # type: ignore[import-untyped]
        validate_mime(file_bytes)
        preprocessed = preprocess(file_bytes)
        b64 = to_base64(preprocessed)
    except (ValueError, RuntimeError) as exc:
        row["error"] = f"image error: {exc}"
        return row

    try:
        from services.ocr_service import extract_fields  # type: ignore[import-untyped]
        async with sem:
            ocr_fields = await extract_fields(b64, client=client)
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"ocr error: {exc}"
        return row

    # --- Parse predictions ---
    pred_total: Decimal | None = parse_monto(ocr_fields.get("monto"))
    pred_date = parse_fecha(ocr_fields.get("fecha"))

    row["pred_total"] = str(pred_total) if pred_total is not None else ""
    row["pred_date"] = str(pred_date) if pred_date is not None else ""

    # --- Match ---
    mt = _match_total(pred_total, gt_total)
    md = _match_date(pred_date, gt_date)
    row["match_total"] = "" if mt is None else str(mt)
    row["match_date"] = "" if md is None else str(md)

    return row


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------


async def _run(
    images: list[Path],
    annotations_dir: Path,
    output_csv: Path,
    concurrency: int,
) -> int:
    """Ejecuta el pipeline sobre todas las imágenes pendientes.

    Returns:
        Exit code: 0 OK, 1 error fatal.
    """
    client = get_ocr_client()

    # Verificar conectividad antes de procesar
    if not await _check_server_reachable(client):
        from config import settings  # type: ignore[import-untyped]
        print(
            f"ERROR: llama-server unreachable at {settings.llama_server_url}",
            file=sys.stderr,
        )
        await client.aclose()
        return 1

    sem = asyncio.Semaphore(concurrency)

    # Abrir CSV en append mode
    is_new_file = not output_csv.exists()
    try:
        csv_fh = output_csv.open("a", newline="", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: no se pudo abrir CSV para escritura — {exc}", file=sys.stderr)
        await client.aclose()
        return 1

    try:
        writer = csv.DictWriter(csv_fh, fieldnames=_CSV_COLUMNS)
        if is_new_file:
            writer.writeheader()

        tasks = [
            _process_image(img, annotations_dir, sem, client)
            for img in images
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                # Unexpected exception — log and continue
                print(f"  WARNING: tarea falló inesperadamente — {result}", file=sys.stderr)
                continue
            writer.writerow(result)
            csv_fh.flush()
            status_parts = []
            if result["error"]:
                status_parts.append(f"ERROR: {result['error']}")
            else:
                status_parts.append(
                    f"total={result['match_total'] or 'None'} "
                    f"date={result['match_date'] or 'None'}"
                )
            print(f"  [{result['image_id']}] {' | '.join(status_parts)}")

    finally:
        csv_fh.close()
        await client.aclose()

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluación batch del pipeline OCR sobre el dataset SROIE.\n"
            "Lee imágenes SROIE y anotaciones, extrae campos vía OCR y\n"
            "guarda resultados en CSV con columnas match_total/match_date."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--images-dir",
        required=True,
        metavar="PATH",
        help="Directorio con imágenes SROIE (*.jpg)",
    )
    parser.add_argument(
        "--annotations-dir",
        required=True,
        metavar="PATH",
        help="Directorio con archivos de anotación SROIE (*.txt, formato key:value)",
    )
    parser.add_argument(
        "--output-csv",
        default="results/sroie_results.csv",
        metavar="PATH",
        help="Ruta del CSV de resultados (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        metavar="INT",
        help="Límite de requests OCR concurrentes — asyncio.Semaphore (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    images_dir = Path(args.images_dir)
    annotations_dir = Path(args.annotations_dir)
    output_csv = Path(args.output_csv)

    # Recopilar imágenes
    if not images_dir.is_dir():
        print(f"ERROR: --images-dir no existe o no es un directorio: {images_dir!r}", file=sys.stderr)
        return 1

    all_images = sorted(images_dir.glob("*.jpg"))
    if not all_images:
        print(f"ERROR: no se encontraron imágenes *.jpg en {images_dir!r}", file=sys.stderr)
        return 1

    # Checkpoint: filtrar imágenes ya procesadas
    processed_ids = _load_processed_ids(output_csv)
    pending_images = [img for img in all_images if img.stem not in processed_ids]

    print(f"SROIE eval: {len(all_images)} imágenes totales, {len(processed_ids)} ya procesadas, {len(pending_images)} pendientes.")

    if not pending_images:
        print("Nada nuevo que procesar. CSV ya está completo.")
        return 0

    # Crear directorio de resultados si no existe
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    return asyncio.run(
        _run(
            images=pending_images,
            annotations_dir=annotations_dir,
            output_csv=output_csv,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
