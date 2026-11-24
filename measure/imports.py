from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from measure.provenance import measurement_row_key, parse_measurement_row


@dataclass(frozen=True)
class RevisionInput:
    trial_id: str
    role: str
    rows: Sequence[Mapping]
    parent_id: int | None = None


def parse_measurement_rows(protocol, role, raw_rows):
    allowed_draws = {draw.name for draw in protocol.draws[protocol.role_index(role)]}
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)) or not raw_rows:
        raise ValueError('expected a nonempty batch of measurements')
    rows = {}
    for raw in raw_rows:
        row = parse_measurement_row(raw)
        key = measurement_row_key(row)
        if key in rows:
            raise ValueError('duplicate measurement source in the batch')
        if row.draw not in allowed_draws:
            raise ValueError('measurement references a draw outside this station')
        rows[key] = row
    return tuple(rows[key] for key in sorted(rows))


def record_revision(store, revision_input):
    protocol = store.registry.get_protocol(revision_input.trial_id)
    rows = parse_measurement_rows(protocol, revision_input.role, revision_input.rows)
    return store.add_revision(protocol, revision_input.role, rows, revision_input.parent_id)
