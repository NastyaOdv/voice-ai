from sqlalchemy import ColumnElement, inspect

from app.db.async_session_manager import Base


def parse_order_by(model: type[Base], order_by: list[str]) -> list[ColumnElement]:
    columns = inspect(model).columns
    expressions: list[ColumnElement] = []
    for raw in order_by:
        token = raw.strip()
        if not token:
            continue
        descending = token[0] == "-"
        if token[0] in "+-":
            token = token[1:]
        if token not in columns:
            continue  # unknown column -> skip it, no error
        column = columns[token]
        expressions.append(column.desc() if descending else column.asc())
    return expressions
