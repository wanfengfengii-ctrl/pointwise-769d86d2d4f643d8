import json
from dataclasses import dataclass

from design.protocol import Protocol
from design.registry import ProtocolRegistry
from measure.provenance import MeasurementRow, measurement_row_key, parse_measurement_row
from storage import database_id, write_transaction
from values import canonical_json


@dataclass(frozen=True)
class MeasurementRevision:
    revision_id: int
    protocol: Protocol
    role: str
    parent_id: int | None
    rows: tuple[MeasurementRow, ...]


class RevisionStore:
    def __init__(self, db):
        self.db = db
        self.registry = ProtocolRegistry(db)
        db.execute('''CREATE TABLE IF NOT EXISTS measurement_revisions (
            revision_id INTEGER PRIMARY KEY,
            trial_id TEXT NOT NULL REFERENCES protocols(trial_id),
            role TEXT NOT NULL,
            parent_id INTEGER REFERENCES measurement_revisions(revision_id),
            snapshot TEXT NOT NULL
        )''')
        db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS first_station_revision
            ON measurement_revisions(trial_id, role) WHERE parent_id IS NULL''')

    def get_revision(self, revision_id):
        database_id(revision_id, 'revision id')
        saved = self.db.execute('''SELECT trial_id, role, parent_id, snapshot
            FROM measurement_revisions WHERE revision_id = ?''', (revision_id,)).fetchone()
        if saved is None:
            raise KeyError(f'unknown revision {revision_id}')
        trial_id, role, parent_id, snapshot = saved
        rows = tuple(parse_measurement_row(row) for row in json.loads(snapshot))
        return MeasurementRevision(revision_id, self.registry.get_protocol(trial_id), role, parent_id, rows)

    def add_revision(self, protocol, role, rows, parent_id=None):
        stored = self.registry.get_protocol(protocol.trial_id)
        if stored != protocol:
            raise ValueError('revision protocol differs from the registered protocol')
        names = {draw.name for draw in stored.draws[stored.role_index(role)]}
        changes = {}
        for row in rows:
            key = measurement_row_key(row)
            if key in changes or row.draw not in names:
                raise ValueError('invalid revision row identity or draw')
            changes[key] = row
        if not changes:
            raise ValueError('empty revision')
        with write_transaction(self.db):
            if parent_id is None:
                existing = self.db.execute('''SELECT 1 FROM measurement_revisions
                    WHERE trial_id = ? AND role = ? AND parent_id IS NULL''',
                    (stored.trial_id, role)).fetchone()
                if existing:
                    raise ValueError('station already has an initial revision')
                snapshot = changes
            else:
                parent = self.get_revision(parent_id)
                if parent.protocol != stored or parent.role != role:
                    raise ValueError('parent belongs to another trial or role')
                snapshot = {measurement_row_key(row): row for row in parent.rows}
                if not changes.keys() <= snapshot.keys():
                    raise ValueError('correction references an unknown measurement source')
                snapshot.update(changes)
            frozen_rows = tuple(snapshot[key] for key in sorted(snapshot))
            payload = canonical_json([row.as_dict() for row in frozen_rows])
            cursor = self.db.execute('''INSERT INTO measurement_revisions
                (trial_id, role, parent_id, snapshot) VALUES (?, ?, ?, ?)''',
                (stored.trial_id, role, parent_id, payload))
            revision = MeasurementRevision(cursor.lastrowid, stored, role, parent_id, frozen_rows)
        return revision
