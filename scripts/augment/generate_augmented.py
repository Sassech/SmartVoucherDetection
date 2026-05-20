"""Generador de imágenes augmentadas para entrenamiento de SmartVoucherDetection.

Aplica degradaciones visuales realistas sobre imágenes fuente (raw o sintéticas)
para simular condiciones reales: reenvíos WhatsApp, fotos en ángulo, poca luz, etc.

Soporta dos modos de input (detección automática):
  - **Sintético**: imágenes PNG de generate_synthetic.py con GT por nombre
    (syn-bbva-0001.png ↔ syn-bbva-0001.json). Matching por stem directo.
  - **Raw**: imágenes JPEG/PDF con GT posicional (mx-001…mx-030).

Flujo principal:
    1. Leer imágenes desde --input-dir (excluyendo misc/).
    2. Convertir PDFs a PNG si es necesario (modo raw).
    3. Mapear cada imagen a su banco usando los JSONs de ground-truth (--gt-dir).
    4. Calcular cuántas variantes generar por banco:
       - Floor mínimo: 30 por banco.
       - Resto de N distribuido proporcionalmente al conteo fuente de cada banco.
    5. Generar variantes con combinaciones aleatorias de degradaciones visuales.
    6. Guardar en --output-dir con nombre: aug-{banco_slug}-{source_id}-{variant:03d}.jpg

Uso (sintéticas — default):
    uv run python scripts/augment/generate_augmented.py \\
        --input-dir dataset/bancario-mx/synthetic/images/ \\
        --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \\
        --output-dir dataset/augmented/ \\
        --n 500 --seed 42

Uso (raw):
    uv run python scripts/augment/generate_augmented.py \\
        --input-dir dataset/bancario-mx/raw/ \\
        --gt-dir dataset/bancario-mx/ground-truth/ \\
        --output-dir dataset/augmented/ \\
        --n 500 --seed 42

Exit 0: éxito (al menos una imagen generada).
Exit 1: error (no se encontraron imágenes, argumentos inválidos, fallo de conversión).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# Bootstrap: inserta api/ en sys.path para reutilizar services/ si es necesario.
# Sigue el mismo patrón que anonymize_comprobante.py y _shared.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Mapa de normalización de nombres de banco
# ---------------------------------------------------------------------------

BANCO_NORM: dict[str, str] = {
    "Mercado Pago WALLET": "Mercado Pago",
    "WALLET": "Mercado Pago",
    "Mercado Pago": "Mercado Pago",
    "BBVA Bancomer": "BBVA",
    "BBVA BANCOMER": "BBVA",
    "BANCOMER": "BBVA",
    "BBVA": "BBVA",
    "BANAMEX": "Banamex",
    "Banamex": "Banamex",
    "Citibanamex": "Banamex",
    "Santander": "Santander",
    "BANORTE": "Banorte",
    "Banorte": "Banorte",
    "SCOTIABANK": "Scotiabank",
    "SCTIABANK": "Scotiabank",   # typo documentado en raw GT
    "Scotiabank": "Scotiabank",
    "Banco Azteca": "Banco Azteca",
}

# Extensiones de imagen soportadas para lectura
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".pdf"})


# ---------------------------------------------------------------------------
# Tipos internos
# ---------------------------------------------------------------------------


class SourceImage(NamedTuple):
    """Imagen raw anotada con su banco normalizado y su ID de ground-truth."""

    path: Path
    gt_id: str      # e.g. "mx-001"
    banco: str      # nombre normalizado, e.g. "Mercado Pago"


# ---------------------------------------------------------------------------
# Conversión PDF → PNG
# ---------------------------------------------------------------------------


def _pdf_to_image(pdf_bytes: bytes) -> bytes:
    """Convierte la primera página de un PDF a PNG bytes.

    Usa la misma función pdf_to_image() de services.image_service que
    anonymize_comprobante.py — mantiene consistencia entre ambos pipelines.
    Requiere que api/ esté en sys.path (lo hace setup_api_path()).
    """
    _setup_api_path()
    from services.image_service import pdf_to_image  # type: ignore[import-untyped]
    return pdf_to_image(pdf_bytes)


_api_path_added = False


def _setup_api_path() -> None:
    """Inserta api/ en sys.path. Idempotente."""
    global _api_path_added
    if _api_path_added:
        return
    api_dir = str(Path(__file__).resolve().parent.parent.parent / "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    _api_path_added = True


def _load_image_bytes(image_path: Path) -> bytes:
    """Lee la imagen como bytes, convirtiendo PDF → PNG si es necesario.

    Para archivos PDF llama a pdf_to_image() (primera página, 300dpi).
    Para JPEG/PNG devuelve los bytes crudos.
    """
    raw = image_path.read_bytes()
    if image_path.suffix.lower() == ".pdf":
        return _pdf_to_image(raw)
    return raw


# ---------------------------------------------------------------------------
# Recolección de fuentes e inferencia de banco
# ---------------------------------------------------------------------------


def _collect_raw_images(input_dir: Path) -> list[Path]:
    """Devuelve imágenes raw del directorio, excluyendo la subcarpeta misc/.

    Los archivos se ordenan para que la enumeración sea determinista.
    """
    images: list[Path] = []
    for p in sorted(input_dir.iterdir()):
        if p.is_dir():
            # Excluir misc/ (imágenes sin etiqueta o de calidad incierta)
            continue
        if p.suffix.lower() in _IMAGE_EXTENSIONS:
            images.append(p)
    return images


def _load_gt_map(gt_dir: Path) -> dict[str, str]:
    """Construye un dict {filename_stem → banco_normalizado} desde los JSONs GT.

    La clave es el ID del GT (ej. "mx-001"), no el nombre del archivo raw —
    la correspondencia se resuelve en _match_image_to_gt().
    """
    gt_map: dict[str, str] = {}
    for jf in sorted(gt_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: no se pudo leer GT {jf.name}: {exc}", file=sys.stderr)
            continue
        banco_raw = data.get("banco_emisor", "")
        banco_norm = BANCO_NORM.get(banco_raw, banco_raw)
        gt_id = data.get("id", jf.stem)
        gt_map[gt_id] = banco_norm
    return gt_map


def _is_synthetic_input(images: list[Path], gt_map: dict[str, str]) -> bool:
    """Detecta si el input es sintético (syn-*) o raw (UUID/nombres largos).

    Heurística: si al menos el 50% de los stems de las imágenes coinciden con
    IDs en el gt_map, es modo sintético (matching por stem directo).
    En modo raw los stems son UUIDs y no coinciden nunca con mx-NNN.
    """
    if not images or not gt_map:
        return False
    matches = sum(1 for img in images if img.stem in gt_map)
    return matches / len(images) >= 0.5


def _match_sources(raw_images: list[Path], gt_map: dict[str, str]) -> list[SourceImage]:
    """Asocia cada imagen con su banco via GT.

    Detecta automáticamente el modo:
    - **Sintético**: matching directo por stem (syn-bbva-0001.png ↔ syn-bbva-0001.json).
    - **Raw**: matching posicional (imagen N-ésima ↔ GT mx-{N:03d}).
    """
    synthetic = _is_synthetic_input(raw_images, gt_map)
    sources: list[SourceImage] = []

    if synthetic:
        # Modo sintético: matching directo por stem
        print("  Modo detectado: SINTÉTICO (matching por nombre)")
        for img_path in raw_images:
            stem = img_path.stem
            if stem in gt_map:
                sources.append(SourceImage(path=img_path, gt_id=stem, banco=gt_map[stem]))
            else:
                print(
                    f"  WARN: {img_path.name} sin GT correspondiente, omitida.",
                    file=sys.stderr,
                )
    else:
        # Modo raw: matching posicional (imagen N → GT mx-{N:03d})
        print("  Modo detectado: RAW (matching posicional)")
        sorted_gt = sorted(gt_map.keys())
        for idx, img_path in enumerate(raw_images):
            if idx < len(sorted_gt):
                gt_id = sorted_gt[idx]
                banco = gt_map[gt_id]
            else:
                print(
                    f"  WARN: {img_path.name} no tiene GT correspondiente, omitida.",
                    file=sys.stderr,
                )
                continue
            sources.append(SourceImage(path=img_path, gt_id=gt_id, banco=banco))

    return sources


# ---------------------------------------------------------------------------
# Distribución de cuotas por banco
# ---------------------------------------------------------------------------


def _compute_quotas(sources: list[SourceImage], n: int, floor: int = 30) -> dict[str, int]:
    """Calcula cuántas imágenes generar por banco.

    Estrategia:
    - floor_min (default 30) por banco → reserva total = n_bancos * floor
    - El remanente (n − reserva) se distribuye proporcionalmente al conteo raw.
    - Si n < n_bancos * floor, todos los bancos reciben floor (el total excede n;
      se acepta como trade-off — consistencia > exactitud de N).

    Args:
        sources:  Lista de imágenes raw anotadas con banco.
        n:        Total de imágenes augmentadas a generar.
        floor:    Mínimo garantizado por banco.

    Returns:
        Dict {banco_nombre: cuota_entero}.
    """
    from collections import Counter

    raw_counts: Counter[str] = Counter(s.banco for s in sources)
    banks = list(raw_counts.keys())
    n_banks = len(banks)

    reserved = n_banks * floor
    remainder = max(0, n - reserved)

    total_raw = sum(raw_counts.values())
    quotas: dict[str, int] = {}

    for bank in banks:
        proportional = math.floor(remainder * raw_counts[bank] / total_raw) if total_raw > 0 else 0
        quotas[bank] = floor + proportional

    # Ajuste fino: el floor() acumulado puede dejar unidades sin asignar
    # (por truncamiento). Las asignamos al banco con mayor conteo raw.
    assigned = sum(quotas.values())
    leftover = n - assigned
    if leftover > 0:
        # Ordenar por conteo raw desc para asignar primero al banco mayor
        ranked = sorted(banks, key=lambda b: raw_counts[b], reverse=True)
        for bank in ranked:
            if leftover <= 0:
                break
            quotas[bank] += 1
            leftover -= 1

    return quotas


# ---------------------------------------------------------------------------
# Degradaciones (augmentations)
# ---------------------------------------------------------------------------


def _build_augment_pipeline(rng: random.Random):  # type: ignore[return]
    """Construye la lista de transformaciones disponibles con sus parámetros.

    Cada degradación está documentada con:
    - Escenario real que simula.
    - Rangos de parámetros.
    - Por qué esos rangos.

    Retorna una lista de callables (image: np.ndarray) → np.ndarray.
    """
    import albumentations as A  # type: ignore[import-untyped]
    import numpy as np

    transforms: list[A.BasicTransform] = [
        # ------------------------------------------------------------------
        # Rotación ±15°
        # Simula: comprobante fotografiado con el teléfono no perfectamente
        # alineado — caso muy frecuente en WhatsApp (el usuario sostiene el
        # teléfono con una sola mano mientras captura).
        # Rango ±15°: suficiente para cubrir la varianza real observada en los
        # raw; más de 20° hace que el texto salga del frame y la imagen pierde
        # información verificable.
        # ------------------------------------------------------------------
        A.Rotate(
            limit=15,
            border_mode=0,        # replicate border con negro (cv2.BORDER_CONSTANT)
            p=0.7,
        ),

        # ------------------------------------------------------------------
        # Recompresión JPEG q=40–70
        # Simula: múltiples reenvíos por WhatsApp o Telegram comprimen la imagen
        # progresivamente. El rango 40–70 reproduce la pérdida típica tras 2–4
        # reenvíos sin llegar a artefactos extremos que harían el texto ilegible.
        # Por debajo de 40 el OCR empieza a fallar — lo evitamos intencionalmente.
        # ------------------------------------------------------------------
        A.ImageCompression(
            quality_range=(40, 70),
            compression_type="jpeg",
            p=0.6,
        ),

        # ------------------------------------------------------------------
        # Ruido Gaussiano σ=10–25
        # Simula: cámara de teléfono en condiciones de poca luz (restaurante,
        # casa con iluminación tenue). σ=10–25 en escala 0–255 equivale a
        # ruido perceptible pero que no oculta los dígitos del monto/banco.
        # ------------------------------------------------------------------
        A.GaussNoise(
            std_range=(10.0 / 255.0, 25.0 / 255.0),  # albumentations ≥ 2.0: std_range en [0,1]
            p=0.5,
        ),

        # ------------------------------------------------------------------
        # Desenfoque Gaussiano kernel 3×3
        # Simula: foto sacada en movimiento o con leve temblor de pulso.
        # Kernel 3×3 (blur_limit=(3,3)) es un desenfoque leve que no destruye
        # legibilidad pero añade varianza suficiente para entrenar robustez.
        # ------------------------------------------------------------------
        A.GaussianBlur(
            blur_limit=(3, 3),
            p=0.4,
        ),

        # ------------------------------------------------------------------
        # Distorsión de perspectiva (perspective warp)
        # Simula: foto tomada desde un ángulo en lugar de perpendicular a la
        # pantalla — el plano del comprobante aparece trapezoidal. El parámetro
        # scale=(0.02, 0.08) controla la magnitud del warp: 0.02 es casi
        # imperceptible; 0.08 es un ángulo notable pero sin pérdida severa
        # de texto en los bordes.
        # ------------------------------------------------------------------
        A.Perspective(
            scale=(0.02, 0.08),
            p=0.5,
        ),

        # ------------------------------------------------------------------
        # Cambio de brillo y contraste
        # Simula: flash del teléfono sobreexpuesto (comprobante muy brillante)
        # o entorno oscuro sin flash (comprobante subexpuesto). Los límites
        # brightness_limit=(-0.2, 0.3) y contrast_limit=(-0.15, 0.25) cubren
        # ambos extremos sin destruir la distinción entre texto y fondo.
        # ------------------------------------------------------------------
        A.RandomBrightnessContrast(
            brightness_limit=(-0.2, 0.3),
            contrast_limit=(-0.15, 0.25),
            p=0.6,
        ),

        # ------------------------------------------------------------------
        # Downscale + upscale (degradación de resolución)
        # Simula: reenvío por WhatsApp o Telegram que reduce la resolución
        # antes de volver a escalar para mostrarla. El rango scale=(0.5, 0.8)
        # significa que la imagen se reduce al 50–80% de su tamaño original
        # y luego se vuelve a escalar a las dimensiones originales, dejando
        # artefactos de interpolación característicos del sharing móvil.
        # ------------------------------------------------------------------
        A.Downscale(
            scale_range=(0.5, 0.8),
            interpolation_pair={
                "downscale": 3,   # cv2.INTER_AREA — mejor para reducción
                "upscale": 2,     # cv2.INTER_CUBIC — suaviza el upscaling
            },
            p=0.4,
        ),
    ]

    return transforms


def _apply_degradations(
    img_bytes: bytes,
    transforms: list,  # list[A.BasicTransform]
    rng: random.Random,
    seed: int,
) -> bytes:
    """Aplica una combinación aleatoria de las degradaciones a la imagen.

    La imagen se convierte a numpy array RGB, se aplican las transformaciones
    y se vuelve a codificar como JPEG con calidad 85 (sin EXIF).

    Args:
        img_bytes:   Imagen como bytes (JPEG o PNG).
        transforms:  Lista de A.BasicTransform disponibles.
        rng:         Instancia de random.Random para reproducibilidad.
        seed:        Semilla numérica para Albumentations (determinismo).

    Returns:
        Imagen augmentada como JPEG bytes.
    """
    import albumentations as A  # type: ignore[import-untyped]
    import numpy as np
    from PIL import Image

    # Cargar imagen como numpy array RGB
    with Image.open(io.BytesIO(img_bytes)) as pil_img:
        img_arr = np.array(pil_img.convert("RGB"))

    # Seleccionar una combinación aleatoria de transformaciones
    # (entre 1 y len(transforms)) — cada una se activa según su p interno
    n_pick = rng.randint(1, len(transforms))
    selected = rng.sample(transforms, k=n_pick)

    pipeline = A.Compose(selected)
    result = pipeline(image=img_arr, seed=seed)
    aug_arr: np.ndarray = result["image"]

    # Codificar como JPEG (calidad 85, sin EXIF)
    out_img = Image.fromarray(aug_arr, mode="RGB")
    buf = io.BytesIO()
    out_img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Slug de banco para nombres de archivo
# ---------------------------------------------------------------------------


def _banco_slug(banco: str) -> str:
    """Convierte nombre de banco a slug ASCII lowercase para nombres de archivo.

    Ejemplos:
        "Mercado Pago"  → "mercado-pago"
        "BBVA"          → "bbva"
        "Banco Azteca"  → "banco-azteca"
    """
    slug = banco.lower()
    # Reemplazar caracteres no alfanuméricos por guión
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Eliminar guiones al inicio/final
    slug = slug.strip("-")
    return slug


# ---------------------------------------------------------------------------
# Generación principal
# ---------------------------------------------------------------------------


def _generate(
    sources: list[SourceImage],
    quotas: dict[str, int],
    output_dir: Path,
    rng: random.Random,
    base_seed: int,
) -> dict[str, int]:
    """Genera todas las imágenes augmentadas.

    Args:
        sources:     Lista de imágenes raw con metadatos.
        quotas:      Dict {banco: cantidad_a_generar}.
        output_dir:  Directorio destino.
        rng:         RNG global (reproducible).
        base_seed:   Semilla base para derivar seeds por variante.

    Returns:
        Dict {banco: cantidad_generada} para el resumen final.
    """
    # Importar aquí para que el --help no falle si albumentations no está
    transforms = _build_augment_pipeline(rng)

    # Agrupar fuentes por banco
    by_bank: dict[str, list[SourceImage]] = {}
    for src in sources:
        by_bank.setdefault(src.banco, []).append(src)

    generated: dict[str, int] = {banco: 0 for banco in quotas}
    total_errors = 0

    # Cache de bytes de imagen cargados: cada archivo fuente se convierte
    # (PDF→PNG) una sola vez y se reutiliza para todas sus variantes.
    # Sin caché, un PDF de 21 archivos se reconvertiría ~10× por banco → timeout.
    img_cache: dict[Path, bytes] = {}

    for banco, quota in sorted(quotas.items()):
        banco_sources = by_bank.get(banco, [])
        if not banco_sources:
            print(f"  WARN: banco '{banco}' sin imágenes fuente — omitido.", file=sys.stderr)
            continue

        slug = _banco_slug(banco)
        print(f"\n  [{banco}] generando {quota} variantes desde {len(banco_sources)} raw...")

        # Pre-cargar todas las fuentes del banco en caché
        print(f"    Cargando {len(banco_sources)} fuentes...")
        loaded_sources: list[tuple[SourceImage, bytes]] = []
        for src in banco_sources:
            if src.path not in img_cache:
                try:
                    img_cache[src.path] = _load_image_bytes(src.path)
                except Exception as exc:  # noqa: BLE001
                    print(f"    ERROR cargando {src.path.name}: {exc}", file=sys.stderr)
                    total_errors += 1
                    continue
            loaded_sources.append((src, img_cache[src.path]))

        if not loaded_sources:
            print(f"    ERROR: no se pudo cargar ninguna fuente para {banco}.", file=sys.stderr)
            continue

        # Ciclar sobre las fuentes para repartir las variantes homogéneamente
        variant_counter = 0
        for i in range(quota):
            src, img_bytes = loaded_sources[i % len(loaded_sources)]

            # Semilla derivada determinista: base + hash(banco) + variant
            variant_seed = base_seed + abs(hash(banco)) % 10_000 + i

            try:
                aug_bytes = _apply_degradations(
                    img_bytes=img_bytes,
                    transforms=transforms,
                    rng=rng,
                    seed=variant_seed,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"    ERROR augmentando {src.path.name}: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            # Nombre de archivo: aug-{banco_slug}-{source_id}-{variant:03d}.jpg
            variant_counter += 1
            out_name = f"aug-{slug}-{src.gt_id}-{variant_counter:03d}.jpg"
            out_path = output_dir / out_name

            try:
                out_path.write_bytes(aug_bytes)
            except OSError as exc:
                print(f"    ERROR guardando {out_name}: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            generated[banco] += 1

            if variant_counter % 50 == 0:
                print(f"    {variant_counter}/{quota} generadas...")

    return generated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera imágenes augmentadas para entrenamiento de SmartVoucherDetection.\n"
            "Lee imágenes de --input-dir (sintéticas o raw), aplica degradaciones\n"
            "realistas y guarda las variantes en --output-dir balanceadas por banco.\n"
            "Detecta automáticamente si el input es sintético (por nombre) o raw (posicional)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        default="dataset/bancario-mx/synthetic/images/",
        metavar="PATH",
        help="Directorio con imágenes fuente (default: %(default)s)",
    )
    parser.add_argument(
        "--gt-dir",
        default="dataset/bancario-mx/synthetic/ground-truth/",
        metavar="PATH",
        help="Directorio con JSONs de ground-truth (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default="dataset/augmented/",
        metavar="PATH",
        help="Directorio destino para imágenes augmentadas (default: %(default)s)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=500,
        metavar="INT",
        help="Total de imágenes augmentadas a generar (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="INT",
        help="Semilla para reproducibilidad (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    input_dir = Path(args.input_dir)
    gt_dir = Path(args.gt_dir)
    output_dir = Path(args.output_dir)
    n_total = args.n
    seed = args.seed

    # Validar directorios de entrada
    if not input_dir.is_dir():
        print(f"ERROR: --input-dir '{input_dir}' no existe o no es un directorio.", file=sys.stderr)
        return 1
    if not gt_dir.is_dir():
        print(f"ERROR: --gt-dir '{gt_dir}' no existe o no es un directorio.", file=sys.stderr)
        return 1

    # Recopilar imágenes fuente (excluyendo misc/)
    raw_images = _collect_raw_images(input_dir)
    if not raw_images:
        print(f"ERROR: no se encontraron imágenes en '{input_dir}' (excluyendo misc/).", file=sys.stderr)
        return 1

    print(f"Imágenes fuente encontradas: {len(raw_images)}")

    # Cargar mapa GT
    gt_map = _load_gt_map(gt_dir)
    if not gt_map:
        print(f"ERROR: no se encontraron JSONs de ground-truth en '{gt_dir}'.", file=sys.stderr)
        return 1

    print(f"Ground-truth JSONs cargados: {len(gt_map)}")

    # Asociar imágenes con bancos
    sources = _match_sources(raw_images, gt_map)
    if not sources:
        print("ERROR: no se pudo asociar ninguna imagen raw con su banco.", file=sys.stderr)
        return 1

    # Resumen de distribución fuente
    from collections import Counter
    raw_dist = Counter(s.banco for s in sources)
    print(f"\nDistribución fuente ({len(sources)} imágenes, {len(raw_dist)} bancos):")
    for banco, cnt in sorted(raw_dist.items(), key=lambda x: -x[1]):
        print(f"  {banco}: {cnt}")

    # Calcular cuotas
    quotas = _compute_quotas(sources, n_total, floor=30)
    total_planned = sum(quotas.values())
    print(f"\nCuotas planificadas (total: {total_planned}):")
    for banco, q in sorted(quotas.items(), key=lambda x: -x[1]):
        print(f"  {banco}: {q}")

    # Crear directorio destino
    output_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar RNG determinista
    rng = random.Random(seed)

    print(f"\nGenerando imágenes augmentadas en '{output_dir}'...")

    # Generar
    generated = _generate(
        sources=sources,
        quotas=quotas,
        output_dir=output_dir,
        rng=rng,
        base_seed=seed,
    )

    # Resumen final
    total_generated = sum(generated.values())
    print(f"\n{'='*60}")
    print(f"FINALIZADO: {total_generated} imágenes generadas en '{output_dir}'")
    print(f"{'='*60}")
    print("Por banco:")
    for banco, cnt in sorted(generated.items(), key=lambda x: -x[1]):
        slug = _banco_slug(banco)
        print(f"  {banco} ({slug}): {cnt}")

    if total_generated == 0:
        print("ERROR: no se generó ninguna imagen.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
