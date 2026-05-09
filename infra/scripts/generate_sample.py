"""Genera una imagen sintética de comprobante bancario para smoke tests.

Uso:
    uv run --project api python infra/scripts/generate_sample.py

NO sustituye un dataset real — solo valida que el pipeline OCR responde con
texto plano. Para evaluación de precisión (Fase 1, criterio 1.9.2) se
necesitan al menos 20 comprobantes reales.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT_PATH = Path(__file__).parent / "fixtures" / "sample_comprobante.png"

# Datos sintéticos típicos de un comprobante mexicano.
DATA = [
    ("BBVA MÉXICO", 28, "header"),
    ("", 18, None),
    ("COMPROBANTE DE TRANSFERENCIA", 20, "subheader"),
    ("", 16, None),
    ("Fecha:           08/05/2026", 18, None),
    ("Hora:            14:35:22", 18, None),
    ("", 8, None),
    ("Monto:           $ 1,250.00 MXN", 22, "amount"),
    ("", 8, None),
    ("Referencia:      TRX-987654321", 18, None),
    ("Cuenta origen:   **** 4521", 18, None),
    ("Cuenta destino:  **** 8893", 18, None),
    ("Beneficiario:    JUAN PEREZ LOPEZ", 18, None),
    ("", 16, None),
    ("Estado:          OPERACIÓN EXITOSA", 18, "status"),
]


def _load_font(size: int) -> ImageFont.ImageFont:
    """Carga una font monoespaciada disponible en sistemas Linux comunes."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def generate(output: Path = OUTPUT_PATH) -> Path:
    width, height = 800, 600
    img = Image.new("RGB", (width, height), color=(252, 252, 250))
    draw = ImageDraw.Draw(img)

    # Borde simulando ticket impreso.
    draw.rectangle([(8, 8), (width - 8, height - 8)], outline=(40, 40, 40), width=2)

    y = 30
    for text, size, kind in DATA:
        if not text:
            y += size
            continue
        font = _load_font(size)
        color = {
            "header": (12, 64, 140),
            "subheader": (40, 40, 40),
            "amount": (8, 100, 8),
            "status": (8, 100, 8),
        }.get(kind, (20, 20, 20))
        # Centrar header/subheader; resto alineado al margen izquierdo.
        if kind in ("header", "subheader"):
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (width - (bbox[2] - bbox[0])) // 2
        else:
            x = 60
        draw.text((x, y), text, font=font, fill=color)
        y += size + 8

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, format="PNG", optimize=True)
    return output


if __name__ == "__main__":
    path = generate()
    print(f"OK -> {path} ({path.stat().st_size} bytes)")
