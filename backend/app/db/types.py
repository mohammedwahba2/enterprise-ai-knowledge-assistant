"""Custom column types."""

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import Text, cast
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[Sequence[float]]):
    """pgvector `vector(n)` without a driver-level codec.

    Values travel as text (`[0.1,0.2,...]`) and are cast on the server, so asyncpg needs no
    custom type registration and every connection (API, worker, tests) behaves the same.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Dialect) -> Callable[[Sequence[float] | None], str | None]:
        def process(value: Sequence[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(repr(float(x)) for x in value) + "]"

        return process

    def bind_expression(self, bindvalue: Any) -> ColumnElement[Any]:
        return cast(cast(bindvalue, Text), self)


def vector_literal(values: Sequence[float]) -> str:
    """Text form for raw SQL parameters: `CAST(CAST(:q AS text) AS vector)`."""
    return "[" + ",".join(repr(float(x)) for x in values) + "]"
