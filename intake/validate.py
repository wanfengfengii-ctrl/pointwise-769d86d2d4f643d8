import json
from collections import Counter
from dataclasses import dataclass

from design.protocol import validate_roles
from design.shared_draws import draw_names, require_bit
from issue.envelope import StationEnvelope, content_fingerprint, decode_envelope
from issue.evidence import EvidenceCount
from values import object_fields, rational, require_int


@dataclass(frozen=True)
class ValidatedStation:
    envelope: StationEnvelope
    roles: tuple[str, str]
    public_draws: tuple[str, ...]
    private_draw_count: int
    counts: tuple[EvidenceCount, ...]
    fingerprint: str


def _parse_counts(raw_counts, public_count, private_count):
    if not isinstance(raw_counts, list) or len(raw_counts) > 1 << (public_count + private_count):
        raise ValueError('invalid count table size')
    totals = Counter()
    seen = set()
    counts = []
    for raw in raw_counts:
        object_fields(raw, ('public_values', 'quota', 'effect', 'count'))
        values = raw['public_values']
        if not isinstance(values, list) or len(values) != public_count:
            raise ValueError('wrong number of public values in count entry')
        public_values = tuple(require_bit(value) for value in values)
        quota = require_int(raw['quota'], 'evidence quota', 0)
        effect = rational(raw['effect'])
        if raw['effect'] != str(effect):
            raise ValueError('evidence effect must use canonical rational text')
        count = require_int(raw['count'], 'evidence multiplicity', 1)
        key = public_values, quota, effect
        if key in seen:
            raise ValueError('duplicate count entry')
        seen.add(key)
        totals[public_values] += count
        if totals[public_values] > 1 << private_count:
            raise ValueError('count exceeds assignments for the public values')
        counts.append(EvidenceCount(*key, count))
    if counts != sorted(counts):
        raise ValueError('count entries must be ordered')
    return tuple(counts)


def validate_station(wire):
    envelope = decode_envelope(wire)
    raw = object_fields(json.loads(envelope.body),
                        ('roles', 'public_draws', 'private_draw_count', 'counts'))
    roles = validate_roles(raw['roles'])
    if envelope.role not in roles:
        raise ValueError('issuing role is outside the protocol roles')
    public = draw_names(raw['public_draws'])
    private = require_int(raw['private_draw_count'], 'private draw count', 0)
    if list(public) != raw['public_draws'] or len(public) > 3 or len(public) + private > 6:
        raise ValueError('invalid public draw order or station draw count')
    counts = _parse_counts(raw['counts'], len(public), private)
    return ValidatedStation(envelope, roles, public, private, counts, content_fingerprint(envelope))
