"""Generador de vouchers sintéticos para SmartVoucherDetection.

Pipeline:
    1. Faker genera datos financieros MX aleatorios por banco.
    2. Template Jinja2 renderiza el HTML con esos datos.
    3. Playwright captura screenshot → PNG.
    4. Se guarda imagen + ground-truth JSON por cada voucher.

Uso:
    uv run python scripts/augment/generate_synthetic.py --help
    uv run python scripts/augment/generate_synthetic.py \\
        --bank bbva --count 50 --output dataset/bancario-mx/synthetic/ --seed 42

    uv run python scripts/augment/generate_synthetic.py \\
        --bank all --count 25 --output dataset/bancario-mx/synthetic/ --seed 42

Salida:
    dataset/bancario-mx/synthetic/
    ├── images/
    │   ├── syn-bbva-0001.png
    │   └── ...
    └── ground-truth/
        ├── syn-bbva-0001.json
        └── ...

Exit 0: éxito (al menos un voucher generado).
Exit 1: error (banco inválido, fallo de Playwright, argumento inválido).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Bootstrap: inserta la raíz del proyecto en sys.path para importar
# scripts.augment.faker_mx sin requerir instalación del paquete.
# Sigue el mismo patrón que generate_augmented.py.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Viewport por banco (mobile vs A4-ish)
# ---------------------------------------------------------------------------

_BANK_VIEWPORTS: dict[str, dict[str, int]] = {
    "bbva":          {"width": 620,  "height": 900},
    "banorte":       {"width": 390,  "height": 844},
    "santander":     {"width": 720,  "height": 1000},
    "banamex":       {"width": 620,  "height": 900},
    "mercadopago":   {"width": 390,  "height": 844},
    "oxxo":          {"width": 300,  "height": 700},
    "bancoppel":     {"width": 620,  "height": 900},
    "banco-azteca":  {"width": 540,  "height": 900},
}

ALL_BANKS = list(_BANK_VIEWPORTS.keys())

# ---------------------------------------------------------------------------
# Template variable builders
# ---------------------------------------------------------------------------


def _build_template_vars(data: dict[str, Any]) -> dict[str, str]:
    """Construye el dict de variables para renderizar el template Jinja2.

    Mapea los campos del ground-truth a los nombres de placeholder
    usados en cada template HTML.
    """
    from scripts.augment.faker_mx import format_fecha_display, format_fecha_larga, format_monto

    ext = data.get("extended", {})
    monto = data["monto"]
    fecha = data["fecha"]
    comision = ext.get("comision", 0.0)
    iva_comision = ext.get("iva_comision", 0.0)
    importe_total = ext.get("importe_total", monto)

    clabe_emisor = data.get("clabe_emisor_mascara") or "••••••••••••••••••"
    clabe_receptor = data.get("clabe_receptor_mascara") or "••••••••••••••••••"

    return {
        # Monto y moneda
        "monto_fmt": format_monto(monto),
        "monto": f"{monto:.2f}",
        "moneda": data.get("moneda", "MXN"),
        # Fechas
        "fecha": fecha,
        "fecha_display": format_fecha_display(fecha),
        "fecha_larga": format_fecha_larga(fecha),
        "year": str(datetime.strptime(fecha, "%Y-%m-%d").year),
        # Hora
        "hora": data.get("hora", "00:00"),
        # Comprobante / referencia
        "numero_comprobante": data.get("numero_comprobante", ""),
        "numero_referencia": data.get("numero_referencia", ""),
        # Banco
        "banco_emisor": data.get("banco_emisor", ""),
        "banco_receptor": data.get("banco_receptor", ""),
        "banco_emisor_upper": data.get("banco_emisor", "").upper(),
        "banco_receptor_upper": data.get("banco_receptor", "").upper(),
        # CLABE
        "clabe_emisor_mascara": clabe_emisor,
        "clabe_receptor_mascara": clabe_receptor,
        # Personas
        "nombre_ordenante": ext.get("nombre_ordenante", ""),
        "nombre_beneficiario": ext.get("nombre_beneficiario", ""),
        "nombre_ordenante_upper": ext.get("nombre_ordenante", "").upper(),
        "nombre_beneficiario_upper": ext.get("nombre_beneficiario", "").upper(),
        "rfc_ordenante": ext.get("rfc_ordenante", ""),
        # Operación
        "concepto": ext.get("concepto", ""),
        "clave_rastreo": ext.get("clave_rastreo") or "N/A",
        "tipo_operacion": ext.get("tipo_operacion", ""),
        "estatus": ext.get("estatus", "Liquidada"),
        # Folio (Banco Azteca)
        "folio": ext.get("folio") or "000000000",
        # Comisiones (OXXO)
        "comision_fmt": format_monto(comision),
        "iva_comision_fmt": format_monto(iva_comision),
        "total_fmt": format_monto(importe_total),
        # Importe transferido
        "importe_transferido_fmt": format_monto(ext.get("importe_transferido", monto)),
        "importe_total_fmt": format_monto(importe_total),
    }


def _render_template(template_path: Path, vars_dict: dict[str, str]) -> str:
    """Renderiza template Jinja2 con las variables dadas.

    Usa jinja2.Environment con undefined=StrictUndefined para que cualquier
    variable faltante en el template lance UndefinedError inmediatamente,
    evitando imágenes rotas con campos vacíos silenciosos.
    """
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "jinja2 es requerido. Instalá con: uv add --optional scripts jinja2"
        ) from exc

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        undefined=StrictUndefined,
    )
    tpl = env.get_template(template_path.name)
    return tpl.render(**vars_dict)


def _screenshot_html(html_content: str, output_path: Path, viewport: dict[str, int]) -> None:
    """Captura screenshot de HTML via Playwright (Chromium headless).

    Args:
        html_content:  HTML renderizado como string.
        output_path:   Ruta destino del PNG.
        viewport:      Dict con 'width' y 'height'.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "playwright es requerido. Instalá con:\n"
            "  uv add --optional scripts playwright\n"
            "  uv run playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()


def _strip_internal_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Elimina campos internos (prefijo '_') del extended antes de guardar JSON."""
    result = dict(data)
    if "extended" in result:
        ext = dict(result["extended"])
        result["extended"] = {k: v for k, v in ext.items() if not k.startswith("_")}
    return result


# ---------------------------------------------------------------------------
# Generación por banco
# ---------------------------------------------------------------------------


def generate_bank_vouchers(
    banco_slug: str,
    count: int,
    output_dir: Path,
    rng: random.Random,
    seq_offset: int = 0,
    verbose: bool = True,
) -> int:
    """Genera `count` vouchers sintéticos para el banco dado.

    Args:
        banco_slug:   Slug del banco (ej. "bbva").
        count:        Cantidad de vouchers a generar.
        output_dir:   Directorio raíz de salida.
        rng:          RNG reproducible.
        seq_offset:   Desplazamiento del número secuencial (para --bank all).
        verbose:      Si True, imprime progreso.

    Returns:
        Número de vouchers generados exitosamente.
    """
    from scripts.augment.faker_mx import generate_voucher_data

    # Directorios de salida
    images_dir = output_dir / "images"
    gt_dir = output_dir / "ground-truth"
    images_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    # Template para este banco
    templates_dir = Path(__file__).parent / "templates"
    template_name = banco_slug.replace("-", "_")  # banco-azteca → banco_azteca
    template_path = templates_dir / f"{template_name}.html"

    if not template_path.exists():
        print(f"  ERROR: template no encontrado: {template_path}", file=sys.stderr)
        return 0

    viewport = _BANK_VIEWPORTS.get(banco_slug, {"width": 600, "height": 900})
    generated = 0
    errors = 0

    for i in range(1, count + 1):
        seq = seq_offset + i
        if verbose:
            print(f"  Generating {banco_slug.upper()} {i}/{count} (seq {seq:04d})...", end=" ")

        try:
            # 1. Generar datos
            data = generate_voucher_data(banco=banco_slug, rng=rng, seq=seq)

            # 2. Renderizar HTML
            tpl_vars = _build_template_vars(data)
            html = _render_template(template_path, tpl_vars)

            # 3. Screenshot
            voucher_id = data["id"]
            img_path = images_dir / f"{voucher_id}.png"
            _screenshot_html(html, img_path, viewport)

            # 4. Guardar JSON (sin campos internos)
            json_path = gt_dir / f"{voucher_id}.json"
            clean_data = _strip_internal_fields(data)
            json_path.write_text(
                json.dumps(clean_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            generated += 1
            if verbose:
                print(f"OK → {voucher_id}.png")

        except Exception as exc:  # noqa: BLE001
            errors += 1
            if verbose:
                print(f"ERROR: {exc}", file=sys.stderr)

    if errors > 0 and verbose:
        print(f"  WARN: {errors} errores al generar vouchers de {banco_slug}.", file=sys.stderr)

    return generated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="generate_synthetic.py",
        description=(
            "Genera vouchers sintéticos de bancos mexicanos.\n\n"
            "Crea imágenes PNG realistas + ground-truth JSON por voucher.\n"
            "Soporta 8 bancos: bbva, banorte, santander, banamex,\n"
            "                   mercadopago, oxxo, bancoppel, banco-azteca\n"
            "Usa '--bank all' para generar todos en un solo run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--bank",
        default="all",
        metavar="BANK",
        help=(
            "Banco a generar: bbva, banorte, santander, banamex, "
            "mercadopago, oxxo, bancoppel, banco-azteca, o 'all'. "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        metavar="INT",
        help="Cantidad de vouchers por banco (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default="dataset/bancario-mx/synthetic/",
        metavar="PATH",
        help="Directorio raíz de salida (default: %(default)s)",
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Validar banco
    bank_arg = args.bank.lower().strip()
    if bank_arg == "all":
        banks_to_run = ALL_BANKS
    elif bank_arg in ALL_BANKS:
        banks_to_run = [bank_arg]
    else:
        print(
            f"ERROR: banco '{bank_arg}' no reconocido.\n"
            f"Opciones válidas: all, {', '.join(ALL_BANKS)}",
            file=sys.stderr,
        )
        return 1

    if args.count < 1:
        print("ERROR: --count debe ser >= 1.", file=sys.stderr)
        return 1

    output_dir = Path(args.output)
    verbose = not args.quiet

    # Inicializar RNG
    rng = random.Random(args.seed)

    if verbose:
        print(f"SmartVoucherDetection — Synthetic Voucher Generator")
        print(f"  Banks: {', '.join(banks_to_run)}")
        print(f"  Count: {args.count} per bank")
        print(f"  Output: {output_dir}")
        print(f"  Seed: {args.seed}")
        print()

    total_generated = 0
    summary: dict[str, int] = {}

    for banco in banks_to_run:
        if verbose:
            print(f"[{banco.upper()}] Generating {args.count} vouchers...")

        n = generate_bank_vouchers(
            banco_slug=banco,
            count=args.count,
            output_dir=output_dir,
            rng=rng,
            seq_offset=0,
            verbose=verbose,
        )
        summary[banco] = n
        total_generated += n

        if verbose:
            print(f"  [{banco.upper()}] Done: {n}/{args.count} generated.\n")

    # Resumen final
    print("=" * 60)
    print(f"DONE: {total_generated} vouchers generated in '{output_dir}'")
    print("=" * 60)
    print("Per bank:")
    for banco, n in summary.items():
        status = "OK" if n == args.count else f"PARTIAL ({n}/{args.count})"
        print(f"  {banco:20s} {n:4d}  [{status}]")

    images_dir = output_dir / "images"
    gt_dir = output_dir / "ground-truth"
    print(f"\nImages:      {images_dir}")
    print(f"Ground-truth: {gt_dir}")

    if total_generated == 0:
        print("\nERROR: no se generó ningún voucher.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
