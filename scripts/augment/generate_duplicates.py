"""Generador de pares de duplicados controlados para SmartVoucherDetection.

Genera pares de comprobantes bancarios con distribución 30/40/30 ±5%:
  - **exacto** (30%): misma imagen, mismo dato → prueba Capa 1 (hash).
  - **parcial_visual** (40%): imagen degradada (JPEG q=50 + rotación ±3°) → Capa 2/3.
  - **negativo** (30%): vouchers distintos mismo banco+fecha → resistencia falsos positivos.

Soporta dos modos de input (detección automática):
  - **Sintético**: imágenes PNG de generate_synthetic.py con GT por nombre
    (syn-bbva-0001.png ↔ syn-bbva-0001.json). Matching por stem directo.
  - **Anonimizado**: imágenes JPEG con GT posicional (mx-001…mx-N).

Uso:
    uv run python scripts/augment/generate_duplicates.py \\
        --images-dir dataset/bancario-mx/synthetic/images/ \\
        --gt-dir dataset/bancario-mx/synthetic/ground-truth/ \\
        --output-csv dataset/bancario-mx/duplicates/pairs.csv \\
        --output-degraded-dir dataset/bancario-mx/duplicates/degraded/ \\
        --n 50 --seed 42

Exit 0: éxito (≥50 pares, distribución dentro de ±5%).
Exit 1: error (< 50 pares posibles, distribución violada, I/O error).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Extensiones de imagen soportadas
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# Distribución objetivo (fracciones)
_TARGET_EXACTO = 0.30
_TARGET_PARCIAL = 0.40
_TARGET_NEGATIVO = 0.30
_TOLERANCE = 0.05  # ±5%

# Columnas del CSV de salida
_CSV_COLUMNS = [
    "id_a",
    "id_b",
    "tipo_duplicado",
    "capa_esperada",
    "clasificacion_esperada",
    "notas",
]


# ---------------------------------------------------------------------------
# Tipos internos
# ---------------------------------------------------------------------------


class SourceImage(NamedTuple):
    """Imagen anotada con metadatos de ground-truth."""

    path: Path
    gt_id: str       # e.g. "syn-bbva-0001" o "mx-001"
    banco: str       # banco_emisor normalizado
    monto: float     # monto del comprobante
    fecha: str       # fecha en formato raw del GT (e.g. "18/04/2026")


class DuplicatePair(NamedTuple):
    """Par de duplicados con metadatos para el CSV."""

    id_a: str
    id_b: str
    tipo_duplicado: str          # exacto | parcial_visual | negativo
    capa_esperada: str           # capa_1 | capa_2 | ninguna
    clasificacion_esperada: str  # duplicado_exacto | duplicado_parcial | no_duplicado
    notas: str


# ---------------------------------------------------------------------------
# Mapa de normalización de banco (reutilizado de generate_augmented.py)
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
    "SCTIABANK": "Scotiabank",
    "Scotiabank": "Scotiabank",
    "Banco Azteca": "Banco Azteca",
    "OXXO": "OXXO",
    "BanCoppel": "BanCoppel",
    "BANCOPPEL": "BanCoppel",
}


# ---------------------------------------------------------------------------
# Recolección de fuentes y carga de GT
# ---------------------------------------------------------------------------


def _collect_images(images_dir: Path) -> list[Path]:
    """Devuelve imágenes del directorio ordenadas deterministamente."""
    images: list[Path] = []
    for p in sorted(images_dir.iterdir()):
        if p.is_dir():
            continue
        if p.suffix.lower() in _IMAGE_EXTENSIONS:
            images.append(p)
    return images


def _load_gt_full(gt_dir: Path) -> dict[str, dict]:
    """Carga todos los JSONs de ground-truth. Clave: gt_id (stem del archivo)."""
    gt_data: dict[str, dict] = {}
    for jf in sorted(gt_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: no se pudo leer GT {jf.name}: {exc}", file=sys.stderr)
            continue
        gt_id = data.get("id", jf.stem)
        gt_data[gt_id] = data
    return gt_data


def _is_synthetic_input(images: list[Path], gt_data: dict[str, dict]) -> bool:
    """Detecta si el input es sintético (matching por stem) o anonimizado (posicional).

    Misma heurística que generate_augmented.py: si ≥50% de los stems coinciden
    con IDs en el GT, se trata de input sintético.
    """
    if not images or not gt_data:
        return False
    matches = sum(1 for img in images if img.stem in gt_data)
    return matches / len(images) >= 0.5


def _match_sources(
    images: list[Path],
    gt_data: dict[str, dict],
) -> list[SourceImage]:
    """Asocia cada imagen con su GT y extrae banco, monto, fecha.

    Modo sintético: matching por stem (syn-bbva-0001.png ↔ syn-bbva-0001.json).
    Modo anonimizado: matching posicional (imagen N ↔ GT mx-{N:03d}).
    """
    synthetic = _is_synthetic_input(images, gt_data)
    sources: list[SourceImage] = []

    def _extract(img_path: Path, data: dict, gt_id: str) -> SourceImage | None:
        banco_raw = data.get("banco_emisor", "")
        banco = BANCO_NORM.get(banco_raw, banco_raw)
        if not banco:
            print(
                f"  WARN: {img_path.name} sin banco_emisor en GT, omitida.",
                file=sys.stderr,
            )
            return None
        monto = float(data.get("monto", 0.0) or 0.0)
        fecha = data.get("fecha", "") or ""
        return SourceImage(
            path=img_path,
            gt_id=gt_id,
            banco=banco,
            monto=monto,
            fecha=fecha,
        )

    if synthetic:
        print("  Modo detectado: SINTÉTICO (matching por nombre)")
        for img_path in images:
            stem = img_path.stem
            if stem not in gt_data:
                print(
                    f"  WARN: {img_path.name} sin GT correspondiente, omitida.",
                    file=sys.stderr,
                )
                continue
            src = _extract(img_path, gt_data[stem], stem)
            if src:
                sources.append(src)
    else:
        print("  Modo detectado: ANONIMIZADO (matching posicional)")
        sorted_gt_ids = sorted(gt_data.keys())
        for idx, img_path in enumerate(images):
            if idx >= len(sorted_gt_ids):
                print(
                    f"  WARN: {img_path.name} sin GT posicional, omitida.",
                    file=sys.stderr,
                )
                continue
            gt_id = sorted_gt_ids[idx]
            src = _extract(img_path, gt_data[gt_id], gt_id)
            if src:
                sources.append(src)

    return sources


# ---------------------------------------------------------------------------
# Degradación para pares parcial_visual
# ---------------------------------------------------------------------------


def _degrade_image(img_path: Path, rng: random.Random, quality: int = 50) -> bytes:
    """Aplica JPEG recompresión q=quality + rotación ±3° a la imagen.

    Usa Pillow directamente (sin albumentations) para mantener simplicidad.

    Args:
        img_path: Path a la imagen fuente.
        rng:      RNG determinista.
        quality:  Calidad JPEG (default 50).

    Returns:
        Bytes de la imagen degradada en formato JPEG.
    """
    from PIL import Image

    angle = rng.uniform(-3.0, 3.0)

    with Image.open(img_path) as img:
        # Convertir a RGB para garantizar JPEG compatible
        rgb = img.convert("RGB")

        # Rotación ±3° con expand=True y fondo blanco
        rotated = rgb.rotate(angle, expand=True, fillcolor=(255, 255, 255))

        # Recompresión JPEG q=50
        buf = io.BytesIO()
        rotated.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Generación de pares por tipo
# ---------------------------------------------------------------------------


def _generate_exact_pairs(
    sources: list[SourceImage],
    n_exacto: int,
    output_degraded_dir: Path,
    rng: random.Random,
    seq_start: int = 1,
) -> list[DuplicatePair]:
    """Genera pares exactos: copia idéntica renombrada.

    La copia se guarda en output_degraded_dir/../exact/ aunque semánticamente
    son "exactos" — el archivo se coloca junto a las degradadas para que el
    evaluador tenga una ruta unificada. En realidad se guarda en el mismo
    output_degraded_dir por simplicidad (el evaluador sólo necesita el id_b).

    Para exactos, id_b = "dup-exact-{seq:04d}" y el archivo
    se copia a output_degraded_dir/dup-exact-{seq:04d}.jpg
    """
    pairs: list[DuplicatePair] = []
    available = list(sources)
    rng.shuffle(available)

    # Ciclar sobre las fuentes si hay menos fuentes que pares requeridos
    seq = seq_start
    for i in range(n_exacto):
        src = available[i % len(available)]
        dup_id = f"dup-exact-{seq:04d}"
        dest = output_degraded_dir / f"{dup_id}.jpg"

        try:
            shutil.copy(src.path, dest)
        except OSError as exc:
            print(f"  ERROR copiando {src.path.name}: {exc}", file=sys.stderr)
            seq += 1
            continue

        pairs.append(
            DuplicatePair(
                id_a=src.gt_id,
                id_b=dup_id,
                tipo_duplicado="exacto",
                capa_esperada="capa_1",
                clasificacion_esperada="duplicado_exacto",
                notas="copia idéntica",
            )
        )
        seq += 1

    return pairs


def _generate_partial_pairs(
    sources: list[SourceImage],
    n_parcial: int,
    output_degraded_dir: Path,
    rng: random.Random,
    seq_start: int = 1,
) -> list[DuplicatePair]:
    """Genera pares parcial_visual: JPEG q=50 + rotación ±3°."""
    pairs: list[DuplicatePair] = []
    available = list(sources)
    rng.shuffle(available)

    seq = seq_start
    for i in range(n_parcial):
        src = available[i % len(available)]
        dup_id = f"dup-partial-{seq:04d}"
        dest = output_degraded_dir / f"{dup_id}.jpg"

        try:
            degraded_bytes = _degrade_image(src.path, rng)
            dest.write_bytes(degraded_bytes)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR degradando {src.path.name}: {exc}", file=sys.stderr)
            seq += 1
            continue

        # Registrar el ángulo de rotación para la nota (aproximado, no exacto
        # porque el ángulo ya se aplicó internamente al RNG — anotamos el rango)
        angle_note = "JPEG q=50 + rotación ±3°"

        pairs.append(
            DuplicatePair(
                id_a=src.gt_id,
                id_b=dup_id,
                tipo_duplicado="parcial_visual",
                capa_esperada="capa_2",
                clasificacion_esperada="duplicado_parcial",
                notas=angle_note,
            )
        )
        seq += 1

    return pairs


def _generate_negative_pairs(
    sources: list[SourceImage],
    n_negativo: int,
    rng: random.Random,
) -> list[DuplicatePair]:
    """Genera pares negativos: mismo banco + fecha cercana, monto distinto.

    Estrategia:
    1. Agrupar por banco.
    2. Para cada banco, ordenar por fecha para encontrar pares próximos.
    3. Seleccionar pares donde monto_a != monto_b (obligatorio).
    4. Preferir mismo fecha exacta; si no, fecha más cercana disponible.
    """
    from collections import defaultdict

    # Agrupar por banco
    by_banco: dict[str, list[SourceImage]] = defaultdict(list)
    for src in sources:
        by_banco[src.banco].append(src)

    # Construir pool de candidatos: pares (a, b) mismo banco, monto distinto
    candidate_pool: list[tuple[SourceImage, SourceImage, str]] = []  # (a, b, nota)

    for banco, banco_sources in sorted(by_banco.items()):
        if len(banco_sources) < 2:
            continue

        # Ordenar por fecha para facilitar búsqueda de pares próximos
        sorted_sources = sorted(banco_sources, key=lambda s: s.fecha)

        # Generar todos los pares posibles dentro del banco
        for i in range(len(sorted_sources)):
            for j in range(i + 1, len(sorted_sources)):
                a = sorted_sources[i]
                b = sorted_sources[j]

                # Monto DEBE ser distinto (criterio obligatorio)
                if a.monto == b.monto:
                    continue

                # Construir nota descriptiva
                if a.fecha == b.fecha:
                    nota = f"mismo banco {banco} + fecha exacta + monto distinto"
                else:
                    nota = f"mismo banco {banco} + fecha cercana + monto distinto"

                candidate_pool.append((a, b, nota))

    if not candidate_pool:
        return []

    # Priorizar pares con misma fecha (más desafiantes como falsos positivos)
    same_date = [(a, b, n) for a, b, n in candidate_pool if a.fecha == b.fecha]
    diff_date = [(a, b, n) for a, b, n in candidate_pool if a.fecha != b.fecha]

    # Shuffle ambos grupos
    rng.shuffle(same_date)
    rng.shuffle(diff_date)

    # Priorizar same_date primero
    ordered_candidates = same_date + diff_date

    pairs: list[DuplicatePair] = []
    used_ids: set[str] = set()

    for a, b, nota in ordered_candidates:
        if len(pairs) >= n_negativo:
            break

        # Evitar duplicar el mismo id_a o id_b en múltiples pares negativos
        # (aunque no es estrictamente requerido, evita confusión en evaluación)
        if a.gt_id in used_ids or b.gt_id in used_ids:
            continue

        pairs.append(
            DuplicatePair(
                id_a=a.gt_id,
                id_b=b.gt_id,
                tipo_duplicado="negativo",
                capa_esperada="ninguna",
                clasificacion_esperada="no_duplicado",
                notas=nota,
            )
        )
        used_ids.add(a.gt_id)
        used_ids.add(b.gt_id)

    # Si no se alcanzó n_negativo con IDs únicos, relajar la restricción
    if len(pairs) < n_negativo:
        for a, b, nota in ordered_candidates:
            if len(pairs) >= n_negativo:
                break
            # Verificar que este par exacto no esté ya incluido
            already = any(
                p.id_a == a.gt_id and p.id_b == b.gt_id for p in pairs
            )
            if not already:
                pairs.append(
                    DuplicatePair(
                        id_a=a.gt_id,
                        id_b=b.gt_id,
                        tipo_duplicado="negativo",
                        capa_esperada="ninguna",
                        clasificacion_esperada="no_duplicado",
                        notas=nota,
                    )
                )

    return pairs


# ---------------------------------------------------------------------------
# Validación de distribución
# ---------------------------------------------------------------------------


def _validate_distribution(
    pairs: list[DuplicatePair],
    min_total: int = 50,
) -> tuple[bool, str]:
    """Valida que la distribución 30/40/30 ±5% se cumpla.

    Returns:
        (ok, mensaje_error). ok=True si pasa.
    """
    total = len(pairs)
    if total < min_total:
        return False, f"Solo {total} pares generados — se requieren ≥{min_total}"

    n_exacto = sum(1 for p in pairs if p.tipo_duplicado == "exacto")
    n_parcial = sum(1 for p in pairs if p.tipo_duplicado == "parcial_visual")
    n_negativo = sum(1 for p in pairs if p.tipo_duplicado == "negativo")

    pct_exacto = n_exacto / total
    pct_parcial = n_parcial / total
    pct_negativo = n_negativo / total

    errors: list[str] = []

    lo_exacto, hi_exacto = _TARGET_EXACTO - _TOLERANCE, _TARGET_EXACTO + _TOLERANCE
    lo_parcial, hi_parcial = _TARGET_PARCIAL - _TOLERANCE, _TARGET_PARCIAL + _TOLERANCE
    lo_negativo, hi_negativo = _TARGET_NEGATIVO - _TOLERANCE, _TARGET_NEGATIVO + _TOLERANCE

    if not (lo_exacto <= pct_exacto <= hi_exacto):
        errors.append(
            f"exacto={pct_exacto:.1%} (esperado {lo_exacto:.0%}–{hi_exacto:.0%})"
        )
    if not (lo_parcial <= pct_parcial <= hi_parcial):
        errors.append(
            f"parcial_visual={pct_parcial:.1%} (esperado {lo_parcial:.0%}–{hi_parcial:.0%})"
        )
    if not (lo_negativo <= pct_negativo <= hi_negativo):
        errors.append(
            f"negativo={pct_negativo:.1%} (esperado {lo_negativo:.0%}–{hi_negativo:.0%})"
        )

    if errors:
        return False, "Distribución fuera de ±5%: " + "; ".join(errors)

    return True, ""


# ---------------------------------------------------------------------------
# Escritura del CSV
# ---------------------------------------------------------------------------


def _write_csv(pairs: list[DuplicatePair], output_csv: Path) -> None:
    """Escribe el CSV de pares de duplicados."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(
                {
                    "id_a": pair.id_a,
                    "id_b": pair.id_b,
                    "tipo_duplicado": pair.tipo_duplicado,
                    "capa_esperada": pair.capa_esperada,
                    "clasificacion_esperada": pair.clasificacion_esperada,
                    "notas": pair.notas,
                }
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera pares de duplicados controlados para evaluar el motor de detección.\n"
            "Distribución objetivo: 30% exacto / 40% parcial_visual / 30% negativo (±5%).\n"
            "Detecta automáticamente si el input es sintético (por nombre) o anonimizado\n"
            "(posicional)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--images-dir",
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
        "--output-csv",
        default="dataset/bancario-mx/duplicates/pairs.csv",
        metavar="PATH",
        help="Ruta del CSV de salida (default: %(default)s)",
    )
    parser.add_argument(
        "--output-degraded-dir",
        default="dataset/bancario-mx/duplicates/degraded/",
        metavar="PATH",
        help="Directorio para imágenes degradadas (default: %(default)s)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=50,
        metavar="INT",
        help="Total de pares a generar (default: %(default)s, mínimo 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="INT",
        help="Semilla para reproducibilidad (default: %(default)s)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce la salida de progreso al mínimo.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    args = _parse_args(argv)

    images_dir = Path(args.images_dir)
    gt_dir = Path(args.gt_dir)
    output_csv = Path(args.output_csv)
    output_degraded_dir = Path(args.output_degraded_dir)
    n_total = max(args.n, 50)  # Mínimo 50
    seed = args.seed

    # Validar directorios de entrada
    if not images_dir.is_dir():
        print(
            f"ERROR: --images-dir '{images_dir}' no existe o no es un directorio.",
            file=sys.stderr,
        )
        return 1
    if not gt_dir.is_dir():
        print(
            f"ERROR: --gt-dir '{gt_dir}' no existe o no es un directorio.",
            file=sys.stderr,
        )
        return 1

    # Cargar imágenes y ground-truth
    images = _collect_images(images_dir)
    if not images:
        print(
            f"ERROR: no se encontraron imágenes en '{images_dir}'.",
            file=sys.stderr,
        )
        return 1

    print(f"Imágenes fuente encontradas: {len(images)}")

    gt_data = _load_gt_full(gt_dir)
    if not gt_data:
        print(
            f"ERROR: no se encontraron JSONs de ground-truth en '{gt_dir}'.",
            file=sys.stderr,
        )
        return 1

    print(f"Ground-truth JSONs cargados: {len(gt_data)}")

    # Asociar imágenes con metadatos
    sources = _match_sources(images, gt_data)
    if not sources:
        print(
            "ERROR: no se pudo asociar ninguna imagen con su ground-truth.",
            file=sys.stderr,
        )
        return 1

    print(f"Fuentes válidas: {len(sources)}")

    # Calcular distribución de pares
    n_exacto = round(n_total * _TARGET_EXACTO)
    n_parcial = round(n_total * _TARGET_PARCIAL)
    n_negativo = n_total - n_exacto - n_parcial  # Resto para evitar rounding drift

    print(f"\nDistribución planificada ({n_total} pares total):")
    print(f"  exacto:        {n_exacto} ({n_exacto/n_total:.0%})")
    print(f"  parcial_visual: {n_parcial} ({n_parcial/n_total:.0%})")
    print(f"  negativo:      {n_negativo} ({n_negativo/n_total:.0%})")

    # Verificar que hay suficientes fuentes para negativos
    # (necesitamos ≥2 imágenes de algún banco con monto distinto)
    from collections import Counter
    banco_counts = Counter(s.banco for s in sources)
    multi_banco = {b for b, c in banco_counts.items() if c >= 2}
    if not multi_banco:
        print(
            "ERROR: no hay suficientes imágenes por banco para generar pares negativos.\n"
            "Se necesitan ≥2 imágenes del mismo banco con montos distintos.\n"
            f"Bancos disponibles: {dict(banco_counts)}",
            file=sys.stderr,
        )
        return 1

    # Crear directorio de degradadas
    output_degraded_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar RNG determinista
    rng = random.Random(seed)

    print(f"\nGenerando pares de duplicados...")

    # Generar pares exactos
    print(f"  [exacto] generando {n_exacto} pares...")
    exact_pairs = _generate_exact_pairs(
        sources=sources,
        n_exacto=n_exacto,
        output_degraded_dir=output_degraded_dir,
        rng=rng,
        seq_start=1,
    )
    print(f"  [exacto] {len(exact_pairs)} pares generados.")

    # Generar pares parcial_visual
    print(f"  [parcial_visual] generando {n_parcial} pares...")
    partial_pairs = _generate_partial_pairs(
        sources=sources,
        n_parcial=n_parcial,
        output_degraded_dir=output_degraded_dir,
        rng=rng,
        seq_start=1,
    )
    print(f"  [parcial_visual] {len(partial_pairs)} pares generados.")

    # Generar pares negativos
    print(f"  [negativo] generando {n_negativo} pares...")
    negative_pairs = _generate_negative_pairs(
        sources=sources,
        n_negativo=n_negativo,
        rng=rng,
    )
    print(f"  [negativo] {len(negative_pairs)} pares generados.")

    # Combinar todos los pares
    all_pairs = exact_pairs + partial_pairs + negative_pairs

    # Validar distribución y cantidad mínima
    ok, error_msg = _validate_distribution(all_pairs, min_total=50)
    if not ok:
        print(f"\nERROR: {error_msg}", file=sys.stderr)

        # Detalle para diagnóstico
        n_ex = sum(1 for p in all_pairs if p.tipo_duplicado == "exacto")
        n_pa = sum(1 for p in all_pairs if p.tipo_duplicado == "parcial_visual")
        n_ne = sum(1 for p in all_pairs if p.tipo_duplicado == "negativo")
        total = len(all_pairs)
        print(f"  Total generado: {total}", file=sys.stderr)
        print(f"  exacto: {n_ex} ({n_ex/max(total,1):.1%})", file=sys.stderr)
        print(f"  parcial_visual: {n_pa} ({n_pa/max(total,1):.1%})", file=sys.stderr)
        print(f"  negativo: {n_ne} ({n_ne/max(total,1):.1%})", file=sys.stderr)
        print(
            "\nConsejo: use --n con un valor más alto o provea más imágenes fuente "
            "con distintos bancos/montos.",
            file=sys.stderr,
        )
        return 1

    # Escribir CSV
    try:
        _write_csv(all_pairs, output_csv)
    except OSError as exc:
        print(f"ERROR escribiendo CSV '{output_csv}': {exc}", file=sys.stderr)
        return 1

    # Resumen final
    total = len(all_pairs)
    n_ex = sum(1 for p in all_pairs if p.tipo_duplicado == "exacto")
    n_pa = sum(1 for p in all_pairs if p.tipo_duplicado == "parcial_visual")
    n_ne = sum(1 for p in all_pairs if p.tipo_duplicado == "negativo")

    print(f"\n{'='*60}")
    print(f"FINALIZADO: {total} pares generados")
    print(f"{'='*60}")
    print(f"  exacto:         {n_ex} ({n_ex/total:.1%})")
    print(f"  parcial_visual: {n_pa} ({n_pa/total:.1%})")
    print(f"  negativo:       {n_ne} ({n_ne/total:.1%})")
    print(f"\nCSV:           {output_csv}")
    print(f"Degradadas:    {output_degraded_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
