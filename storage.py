import sqlite3
from contextlib import contextmanager

from values import require_int


@contextmanager
def open_database(path):
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        yield db
    finally:
        db.close()


@contextmanager
def write_transaction(db):
    if db.in_transaction:
        raise RuntimeError('a business write requires an idle connection')
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def database_id(value, label):
    require_int(value, label, 1)
    if value > (1 << 63) - 1:
        raise ValueError(f'{label} is outside the storage range')
    return value
