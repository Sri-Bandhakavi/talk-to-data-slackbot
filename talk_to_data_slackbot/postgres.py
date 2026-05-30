from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from talk_to_data_slackbot.config import Settings, get_settings


def connect(settings: Settings | None = None) -> Connection:
    settings = settings or get_settings()
    return psycopg.connect(settings.database_url)


@contextmanager
def connection(settings: Settings | None = None) -> Iterator[Connection]:
    conn = connect(settings)
    try:
        yield conn
    finally:
        conn.close()


def ping(settings: Settings | None = None) -> bool:
    with connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
            return row is not None and row[0] == 1


def execute_read(
    sql: str,
    params: tuple | dict | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    with connection(settings) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
