"""Connection pool. No SQL here; statements live in queries.py."""
import logging
import math
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

log = logging.getLogger("biyahe.db")

_pool: Optional[ConnectionPool] = None


class DatabaseUnavailable(Exception):
    """The database cannot be reached right now (maps to 503 database_unavailable)."""


def make_pool(url: str, timeout_s: float) -> ConnectionPool:
    """Build and open a pool without waiting for the first connection."""
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        timeout=timeout_s,
        open=False,
        check=ConnectionPool.check_connection,  # drop connections broken by a DB restart
        kwargs={"connect_timeout": max(1, math.ceil(timeout_s))},
    )
    pool.open(wait=False)
    return pool


def init_pool(url: str, timeout_s: float) -> None:
    """Open the global pool and wait for a first connection; raises DatabaseUnavailable."""
    global _pool
    pool = make_pool(url, timeout_s)
    try:
        pool.wait(timeout=timeout_s)
    except PoolTimeout as exc:
        pool.close(timeout=0)
        raise DatabaseUnavailable("could not connect within the pool timeout") from exc
    _pool = pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Borrow a connection; commits on success. Connectivity failures become DatabaseUnavailable."""
    if _pool is None:
        raise DatabaseUnavailable("pool is not open")
    try:
        with _pool.connection() as conn:
            yield conn
    except (PoolTimeout, psycopg.OperationalError, psycopg.InterfaceError) as exc:
        log.warning("database unavailable: %s", exc)
        raise DatabaseUnavailable(str(exc)) from exc
