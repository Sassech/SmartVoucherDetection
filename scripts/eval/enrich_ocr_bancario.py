"""Enriquecimiento batch de GTs sintéticos con texto_extraido OCR real.

Flujo por imagen:
    1. Leer GT JSON de --gt-dir (ya generados por generate_synthetic.py)
    2. Si ya tiene texto_extraido no nulo → skip (checkpoint idempotente)
    3. validate_mime() → preprocess() → to_base64() (image_service)
    4. extract_fields(b64) vía GLM-OCR con asyncio.Semaphore(--concurrency)
    5. Escribir campo texto_extraido en el GT JSON (merge in-place, no sobreescribe otros campos)

Progress: imprime [OK], [SKIP] o [ERR] por imagen.
Checkpoint: re-correr el script retoma desde donde quedó.

Uso:
    uv run python scripts/eval/enrich_ocr_bancario.py --help
    uv run python scripts/eval/enrich_ocr_bancario.py \\
        --images-dir dataset/bancario-mx/synthetic/images/ \\
        --gt-dir     dataset/bancario-mx/synthetic/ground-truth/ \\
        --concurrency 2

Exit 0: OK (incluso si algunas imágenes fallaron — ver contadores al final)
Exit 1: error fatal (llama-server inaccesible, directorios inválidos)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Bootstrap: inserta scripts/ y api/ en sys.path
# Funciona tanto con `uv run python` desde la raíz como desde api/
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_API_DIR = _SCRIPTS_DIR.parent / "api"

for _p in (_SCRIPTS_DIR, _API_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Asegurar que las deps de api/ estén disponibles (pydantic_settings, fastapi, etc.)
# Si no están en el venv activo, intentamos el venv de api/
try:
    import pydantic_settings  # noqa: F401
except ModuleNotFoundError:
    import site
    _api_site = _API_DIR / ".venv" / "lib"
    for _sp in sorted(_api_site.glob("python3.*/site-packages")):
        site.addsitedir(str(_sp))

from _shared import get_ocr_client  # noqa: E402


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def _needs_enrichment(gt_path: Path) -> bool:
    """True si el GT existe pero NO tiene texto_extraido (o está vacío)."""
    if not gt_path.exists():
        return False
    try:
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        val = data.get("texto_extraido")
        return val is None or str(val).strip() == ""
    except (OSError, json.JSONDecodeError):
        return False


def _write_texto_extraido(gt_path: Path, texto: str) -> None:
    """Merge in-place: agrega/actualiza solo texto_extraido en el GT JSON."""
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    data["texto_extraido"] = texto
    gt_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------


async def _check_server_reachable(client) -> bool:
    import httpx
    try:
        await client.get("/")
        return True
    except httpx.RequestError:
        return False


# ---------------------------------------------------------------------------
# Core async pipeline per image
# ---------------------------------------------------------------------------


async def _enrich_image(
    image_path: Path,
    gt_path: Path,
    sem: asyncio.Semaphore,
    client,
) -> tuple[str, str]:
    """Ejecuta OCR sobre una imagen y escribe texto_extraido en su GT.

    Returns:
        (image_id, status) donde status es "ok", "skip", o "err:<msg>"
    """
    image_id = image_path.stem

    # Checkpoint: ya enriquecido
    if not _needs_enrichment(gt_path):
        return image_id, "skip"

    # Leer y preprocesar imagen
    try:
        file_bytes = image_path.read_bytes()
    except OSError as exc:
        return image_id, f"err:read:{exc}"

    try:
        from services.image_service import preprocess, to_base64, validate_mime  # type: ignore[import-untyped]
        validate_mime(file_bytes)
        preprocessed = preprocess(file_bytes)
        b64 = to_base64(preprocessed)
    except (ValueError, RuntimeError) as exc:
        return image_id, f"err:image:{exc}"

    # OCR
    try:
        from services.ocr_service import extract_fields  # type: ignore[import-untyped]
        async with sem:
            ocr_fields = await extract_fields(b64, client=client)
    except Exception as exc:  # noqa: BLE001
        return image_id, f"err:ocr:{exc}"

    # extract_fields devuelve campos estructurados, no texto crudo.
    # Para que Layer 3 (TF-IDF cosine) sea útil, construimos un texto plano
    # que represente todo lo que el OCR extrajo — igual que texto_extraido
    # en comprobantes reales procesados por el pipeline de la API.
    parts = [
        str(v)
        for v in ocr_fields.values()
        if v is not None and str(v).strip()
    ]
    texto = " ".join(parts)

    try:
        _write_texto_extraido(gt_path, texto)
    except (OSError, json.JSONDecodeError) as exc:
        return image_id, f"err:write:{exc}"

    return image_id, "ok"


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------


async def _run(
    pairs: list[tuple[Path, Path]],
    concurrency: int,
) -> tuple[int, int, int]:
    """Procesa todos los pares (image_path, gt_path).

    Returns:
        (n_ok, n_skip, n_err)
    """
    client = get_ocr_client()

    if not await _check_server_reachable(client):
        from config import settings  # type: ignore[import-untyped]
        print(
            f"ERROR: llama-server inaccesible en {settings.llama_server_url}",
            file=sys.stderr,
        )
        await client.aclose()
        return 0, 0, len(pairs)

    sem = asyncio.Semaphore(concurrency)
    n_ok = n_skip = n_err = 0

    tasks = [_enrich_image(img, gt, sem, client) for img, gt in pairs]

    # gather con return_exceptions para no abortar en errores parciales
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print(f"  [FATAL] tarea inesperada: {result}", file=sys.stderr)
            n_err += 1
            continue
        image_id, status = result
        if status == "ok":
            n_ok += 1
            print(f"  [OK]   {image_id}")
        elif status == "skip":
            n_skip += 1
            print(f"  [SKIP] {image_id} — ya enriquecido")
        else:
            n_err += 1
            print(f"  [ERR]  {image_id} — {status}", file=sys.stderr)

    await client.aclose()
    return n_ok, n_skip, n_err


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enriquece los GTs sintéticos con texto_extraido real del OCR.\n"
            "Idempotente: re-correr retoma desde el último checkpoint."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--images-dir",
        default="dataset/bancario-mx/synthetic/images/",
        metavar="PATH",
        help="Directorio con imágenes sintéticas PNG (default: %(default)s)",
    )
    parser.add_argument(
        "--gt-dir",
        default="dataset/bancario-mx/synthetic/ground-truth/",
        metavar="PATH",
        help="Directorio con GTs JSON a enriquecer (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        metavar="INT",
        help="Límite de requests OCR concurrentes (default: %(default)s)",
    )
    parser.add_argument(
        "--bank",
        default="all",
        metavar="BANK",
        help="Filtrar por banco (ej: bbva) o 'all' para todos (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    images_dir = Path(args.images_dir)
    gt_dir = Path(args.gt_dir)

    if not images_dir.is_dir():
        print(f"ERROR: --images-dir no existe: {images_dir!r}", file=sys.stderr)
        return 1
    if not gt_dir.is_dir():
        print(f"ERROR: --gt-dir no existe: {gt_dir!r}", file=sys.stderr)
        return 1

    # Recopilar imágenes PNG (sintéticas)
    pattern = f"syn-{args.bank}-*.png" if args.bank != "all" else "syn-*.png"
    all_images = sorted(images_dir.glob(pattern))

    if not all_images:
        print(f"ERROR: no se encontraron imágenes ({pattern}) en {images_dir!r}", file=sys.stderr)
        return 1

    # Construir pares (image, gt) — solo los que tienen GT existente
    pairs: list[tuple[Path, Path]] = []
    missing_gts = 0
    for img in all_images:
        gt = gt_dir / (img.stem + ".json")
        if not gt.exists():
            missing_gts += 1
            continue
        pairs.append((img, gt))

    if missing_gts:
        print(f"WARNING: {missing_gts} imágenes sin GT JSON — se omiten", file=sys.stderr)

    if not pairs:
        print("ERROR: no hay pares (imagen, GT) válidos para procesar", file=sys.stderr)
        return 1

    # Contar pendientes (checkpoint)
    pending = [(img, gt) for img, gt in pairs if _needs_enrichment(gt)]
    already_done = len(pairs) - len(pending)

    print(f"SmartVoucherDetection — OCR Enrichment (bancario-mx sintéticos)")
    print(f"  Imágenes encontradas : {len(all_images)}")
    print(f"  Con GT válido        : {len(pairs)}")
    print(f"  Ya enriquecidos      : {already_done} (checkpoint)")
    print(f"  Pendientes           : {len(pending)}")
    print(f"  Concurrencia         : {args.concurrency}")
    print()

    if not pending:
        print("Nada que procesar — todos los GTs ya tienen texto_extraido.")
        return 0

    n_ok, n_skip, n_err = asyncio.run(_run(pending, args.concurrency))

    print()
    print("=" * 60)
    print(f"FINALIZADO: {n_ok} enriquecidos, {n_skip} saltados, {n_err} errores")
    print("=" * 60)

    if n_err > 0:
        print(
            f"WARNING: {n_err} imágenes fallaron — re-correr el script para reintentar.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
