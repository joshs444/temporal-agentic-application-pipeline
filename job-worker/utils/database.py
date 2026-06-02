"""
Async database utilities for JobHunt API.

Uses asyncpg for async PostgreSQL connections with connection pooling.
"""

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import asyncpg
from asyncpg import Pool, Connection


async def _init_connection(conn: Connection) -> None:
    """Initialize connection with JSON codec."""
    await conn.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)

# Parse DATABASE_URL for asyncpg (it expects components, not URL)
def parse_database_url(url: str) -> dict[str, Any]:
    """Parse DATABASE_URL into asyncpg connection parameters."""
    # Format: postgresql://user:password@host:port/database
    if url.startswith("postgresql://"):
        url = url[13:]
    elif url.startswith("postgres://"):
        url = url[11:]

    # Split user:password@host:port/database
    auth_part, rest = url.split("@")
    user, password = auth_part.split(":")

    if "/" in rest:
        host_port, database = rest.split("/", 1)
    else:
        host_port = rest
        database = "jobhunt_db"

    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 5432

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": database,
    }


# Global connection pool
_pool: Optional[Pool] = None


async def get_pool() -> Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        params = parse_database_url(DATABASE_URL)
        _pool = await asyncpg.create_pool(
            **params,
            min_size=2,
            max_size=10,
            command_timeout=60,
            init=_init_connection,  # Set up JSON/JSONB codecs
        )
    return _pool


async def close_pool() -> None:
    """Close the database connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncGenerator[Connection, None]:
    """Get a database connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def fetch_one(query: str, *args: Any) -> Optional[asyncpg.Record]:
    """Fetch a single row from the database."""
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    """Fetch all rows from the database."""
    async with get_connection() as conn:
        return await conn.fetch(query, *args)


async def execute(query: str, *args: Any) -> str:
    """Execute a query and return the status."""
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def execute_many(query: str, args: list[tuple[Any, ...]]) -> None:
    """Execute a query multiple times with different arguments."""
    async with get_connection() as conn:
        await conn.executemany(query, args)


def record_to_dict(record: Optional[asyncpg.Record]) -> Optional[dict[str, Any]]:
    """Convert an asyncpg Record to a dictionary."""
    if record is None:
        return None
    return dict(record)


def records_to_dicts(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    """Convert a list of asyncpg Records to a list of dictionaries."""
    return [dict(r) for r in records]
