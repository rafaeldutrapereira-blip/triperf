"""
Helpers de paginación cursor-based y X-RateLimit headers para LabX.
Uso en endpoints:
    from .pagination import paginate_query, PaginationParams, rl_headers

    @router.get("/activities")
    def list_activities(p: PaginationParams = Depends(), ...):
        result = paginate_query(db.query(GarminActivity).filter(...), p)
        return result
"""
from __future__ import annotations

from fastapi import Query
from sqlalchemy.orm import Query as SAQuery
from typing import Any


class PaginationParams:
    """Parámetros de paginación offset-based (simple, predecible para la app)."""
    def __init__(
        self,
        page:     int = Query(1,   ge=1,   description="Número de página (empieza en 1)"),
        per_page: int = Query(50,  ge=1,   le=200, description="Items por página (máx 200)"),
    ):
        self.page     = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def paginate_query(query: SAQuery, params: PaginationParams) -> dict[str, Any]:
    """
    Ejecuta query con paginación y devuelve estructura estándar.
    Retorna:
        {
            "items": [...],
            "total": int,
            "page": int,
            "per_page": int,
            "pages": int,
            "has_next": bool,
            "has_prev": bool,
        }
    """
    total = query.count()
    items = query.offset(params.offset).limit(params.limit).all()
    pages = max(1, (total + params.per_page - 1) // params.per_page)
    return {
        "items":    items,
        "total":    total,
        "page":     params.page,
        "per_page": params.per_page,
        "pages":    pages,
        "has_next": params.page < pages,
        "has_prev": params.page > 1,
    }


def rl_headers(max_count: int, current: int, window_seconds: int = 3600) -> dict[str, str]:
    """
    I-10: Genera headers X-RateLimit-* estándar para endpoints con rate limiting.
    Uso: return Response(..., headers=rl_headers(10, count))
    """
    remaining = max(0, max_count - current)
    return {
        "X-RateLimit-Limit":     str(max_count),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Window":    str(window_seconds),
    }
