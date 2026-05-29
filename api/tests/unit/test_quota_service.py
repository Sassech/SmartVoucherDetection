"""Tests for quota_service.check_quota (R-73 / R-74).

Estrategia: unit tests con mock session — aislado de Postgres real.
La funcion check_quota es async, testeada con pytest-asyncio.

Spec coverage:
  R-73: PLAN_LIMITS constant tiene valores correctos para basic/pro/enterprise
  R-74: check_quota retorna None si sin_cuota=True (exento)
  R-74: check_quota retorna None si PLAN_LIMITS[plan] == -1 (ilimitado)
  R-74: check_quota retorna None si count < limite
  R-74: check_quota retorna None si count < limite (at limit boundary minus one)
  R-74: check_quota levanta 429 si count >= limite con detail correcto
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from config import PLAN_LIMITS


# ---------------------------------------------------------------------------
# R-73: PLAN_LIMITS constant
# ---------------------------------------------------------------------------


def test_plan_limits_basic():
    """PLAN_LIMITS['basic'] == 100 (R-73)."""
    assert PLAN_LIMITS["basic"] == 100


def test_plan_limits_pro():
    """PLAN_LIMITS['pro'] == 500 (R-73)."""
    assert PLAN_LIMITS["pro"] == 500


def test_plan_limits_enterprise_is_unlimited():
    """PLAN_LIMITS['enterprise'] == -1, significa ilimitado (R-73)."""
    assert PLAN_LIMITS["enterprise"] == -1


# ---------------------------------------------------------------------------
# R-74: check_quota — paths de exencion
# ---------------------------------------------------------------------------


def _make_usuario(*, plan: str = "basic", sin_cuota: bool = False) -> MagicMock:
    """Construye un mock de Usuario con plan y sin_cuota configurables."""
    user = MagicMock()
    user.plan = plan
    user.sin_cuota = sin_cuota
    user.id_usuario = "mock-uuid-1234"
    return user


def _make_session(*, monthly_count: int) -> AsyncMock:
    """Mock de AsyncSession que retorna monthly_count para scalar()."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = monthly_count

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.mark.asyncio
async def test_check_quota_exempt_user_skips_check():
    """Usuario con sin_cuota=True → retorna None sin consultar DB (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="basic", sin_cuota=True)
    session = AsyncMock()  # execute no debe ser llamado

    result = await check_quota(usuario, session)

    assert result is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_check_quota_enterprise_plan_skips_check():
    """Plan enterprise (PLAN_LIMITS==-1) → retorna None sin consultar DB (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="enterprise", sin_cuota=False)
    session = AsyncMock()

    result = await check_quota(usuario, session)

    assert result is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_check_quota_under_limit_returns_none():
    """Usuario basic con 50 uploads este mes (< 100) → retorna None (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="basic", sin_cuota=False)
    session = _make_session(monthly_count=50)

    result = await check_quota(usuario, session)

    assert result is None


@pytest.mark.asyncio
async def test_check_quota_at_limit_raises_429():
    """Usuario basic con exactamente 100 uploads → levanta HTTP 429 (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="basic", sin_cuota=False)
    session = _make_session(monthly_count=100)

    with pytest.raises(HTTPException) as exc_info:
        await check_quota(usuario, session)

    assert exc_info.value.status_code == 429
    detail = exc_info.value.detail
    assert detail["used"] == 100
    assert detail["limit"] == 100
    assert detail["plan"] == "basic"
    assert "reset_date" in detail


@pytest.mark.asyncio
async def test_check_quota_over_limit_raises_429_with_correct_detail():
    """Usuario pro con 600 uploads (> 500) → 429 con used=600, limit=500 (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="pro", sin_cuota=False)
    session = _make_session(monthly_count=600)

    with pytest.raises(HTTPException) as exc_info:
        await check_quota(usuario, session)

    assert exc_info.value.status_code == 429
    detail = exc_info.value.detail
    assert detail["used"] == 600
    assert detail["limit"] == 500
    assert detail["plan"] == "pro"
    assert "reset_date" in detail


@pytest.mark.asyncio
async def test_check_quota_one_below_limit_passes():
    """Usuario basic con 99 uploads (< 100) → retorna None, no levanta (R-74)."""
    from services.quota_service import check_quota

    usuario = _make_usuario(plan="basic", sin_cuota=False)
    session = _make_session(monthly_count=99)

    result = await check_quota(usuario, session)

    assert result is None
