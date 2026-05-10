"""Deteccion de duplicados: Capa 2 (exact match) y Capa 3 (scoring ponderado).

Decisiones de diseno:
- S_texto = 0.0 cuando cualquiera de los textos es NULL — sin renormalizacion.
  Score maximo sin texto: 0.70 (no alcanza threshold de duplicado 0.90).
- S_monto usa Decimal para evitar errores de punto flotante (D-10).
- find_candidates filtra por id_usuario (misma org) + ventana ±30 dias.
- run_capa2 usa el indice compuesto idx_comp_dedup creado en la migracion.
- run_capa3 siempre retorna (best_or_None, score, clasificacion) — caller
  decide como persistir el resultado.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from Levenshtein import ratio as lev_ratio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Pesos del scoring (suman 1.0)
# ---------------------------------------------------------------------------
W_REF = 0.35
W_TEXT = 0.30
W_MONTO = 0.20
W_FECHA = 0.15

# ---------------------------------------------------------------------------
# Umbrales de clasificacion (Spec CAP-05)
# ---------------------------------------------------------------------------
THRESHOLD_DUPLICADO = 0.90
THRESHOLD_SOSPECHOSO = 0.75

# Ventana de busqueda de candidatos en dias (exactamente 30)
CANDIDATE_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Componentes del score — funciones puras
# ---------------------------------------------------------------------------


def _s_ref(a: str | None, b: str | None) -> float:
    """Levenshtein ratio entre dos referencias. 0.0 si alguna es None."""
    if not a or not b:
        return 0.0
    return lev_ratio(a, b)


def _s_texto(a: str | None, b: str | None) -> float:
    """TF-IDF cosine similarity entre dos textos OCR. 0.0 si alguno es None.

    Segun design: S_texto = 0.0 cuando cualquier texto es NULL — sin
    renormalizacion de pesos. Score maximo sin texto: 0.70.
    """
    if not a or not b:
        return 0.0
    try:
        vec = TfidfVectorizer().fit_transform([a, b])
        return float(cosine_similarity(vec[0], vec[1])[0][0])
    except Exception:  # noqa: BLE001 — vectorizer puede fallar con texto raro
        return 0.0


def _s_monto(a: Decimal | None, b: Decimal | None) -> float:
    """Similitud de monto: 1 - abs(a-b)/max(a,b). Usa Decimal (D-10 rule)."""
    if a is None or b is None:
        return 0.0
    mx = max(abs(float(a)), abs(float(b)))
    if mx == 0:
        return 1.0
    return 1.0 - abs(float(a) - float(b)) / mx


def _s_fecha(a: date | None, b: date | None) -> float:
    """Similitud temporal: 1 - min(dias_diff, 30)/30. 0.0 si alguna es None."""
    if a is None or b is None:
        return 0.0
    delta = abs((a - b).days)
    return 1.0 - min(delta, CANDIDATE_WINDOW_DAYS) / CANDIDATE_WINDOW_DAYS


# ---------------------------------------------------------------------------
# Score y clasificacion
# ---------------------------------------------------------------------------


def compute_score(nuevo: Comprobante, existente: Comprobante) -> float:
    """Score de similitud ponderado entre dos comprobantes. Rango [0.0, 1.0].

    Formula:
        Score = 0.35*S_ref + 0.30*S_texto + 0.20*S_monto + 0.15*S_fecha

    Cuando texto_extraido es NULL en cualquiera, S_texto = 0.0 (no
    renormalizacion). Score maximo sin texto: 0.70.
    """
    return (
        W_REF * _s_ref(nuevo.referencia, existente.referencia)
        + W_TEXT * _s_texto(nuevo.texto_extraido, existente.texto_extraido)
        + W_MONTO * _s_monto(nuevo.monto, existente.monto)
        + W_FECHA * _s_fecha(nuevo.fecha_deposito, existente.fecha_deposito)
    )


def classify(score: float) -> str:
    """Clasifica un score en 'duplicado', 'sospechoso' o 'valido'.

    Umbrales (Spec CAP-05):
        >= 0.90 → duplicado
        >= 0.75 → sospechoso
        < 0.75  → valido
    """
    if score >= THRESHOLD_DUPLICADO:
        return "duplicado"
    if score >= THRESHOLD_SOSPECHOSO:
        return "sospechoso"
    return "valido"


# ---------------------------------------------------------------------------
# Consultas async
# ---------------------------------------------------------------------------


async def find_candidates(
    session: AsyncSession,
    nuevo: Comprobante,
    window_days: int = CANDIDATE_WINDOW_DAYS,
) -> list[Comprobante]:
    """Busca comprobantes del mismo usuario dentro de la ventana de fechas.

    Filtra:
    - Mismo id_usuario (misma organizacion)
    - fecha_deposito en [fecha - window, fecha + window]
    - No soft-deleted (deleted_at IS NULL)
    - Excluye el propio comprobante (id_comprobante != nuevo.id)

    Retorna lista vacia si nuevo.fecha_deposito es None.
    """
    if nuevo.fecha_deposito is None:
        return []

    date_from = nuevo.fecha_deposito - timedelta(days=window_days)
    date_to = nuevo.fecha_deposito + timedelta(days=window_days)

    result = await session.execute(
        select(Comprobante).where(
            and_(
                Comprobante.id_usuario == nuevo.id_usuario,
                Comprobante.id_comprobante != nuevo.id_comprobante,
                Comprobante.fecha_deposito >= date_from,
                Comprobante.fecha_deposito <= date_to,
                Comprobante.deleted_at.is_(None),
            )
        )
    )
    return list(result.scalars().all())


async def run_capa2(
    session: AsyncSession,
    nuevo: Comprobante,
) -> Comprobante | None:
    """Capa 2: exact match en (referencia, monto, fecha_deposito).

    Usa el indice compuesto idx_comp_dedup. Retorna None si cualquier
    campo del trio es None (el indice no aplica para NULLs).

    No crea Validacion — eso es responsabilidad del caller (upload.py).
    """
    if nuevo.referencia is None or nuevo.monto is None or nuevo.fecha_deposito is None:
        return None

    result = await session.execute(
        select(Comprobante)
        .where(
            and_(
                Comprobante.referencia == nuevo.referencia,
                Comprobante.monto == nuevo.monto,
                Comprobante.fecha_deposito == nuevo.fecha_deposito,
                Comprobante.id_comprobante != nuevo.id_comprobante,
                Comprobante.deleted_at.is_(None),
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_capa3(
    session: AsyncSession,
    nuevo: Comprobante,
) -> tuple[Comprobante | None, float, str]:
    """Capa 3: scoring ponderado contra candidatos en ventana.

    Retorna (mejor_match_o_None, mejor_score, clasificacion).
    Si no hay candidatos → (None, 0.0, 'valido').

    No crea Validacion — responsabilidad del caller (upload.py).
    """
    candidates = await find_candidates(session, nuevo)
    if not candidates:
        return None, 0.0, "valido"

    best_comp: Comprobante | None = None
    best_score = 0.0

    for cand in candidates:
        score = compute_score(nuevo, cand)
        if score > best_score:
            best_score = score
            best_comp = cand

    clasificacion = classify(best_score)
    return best_comp, best_score, clasificacion
