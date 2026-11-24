import json
from collections import Counter
from dataclasses import dataclass

from design.protocol import validate_roles
from design.shared_draws import draw_names, require_bit
from issue.envelope import ENVELOPE_V1, ENVELOPE_V2, StationEnvelope, content_fingerprint, decode_envelope
from issue.evidence import EvidenceCount
from issue.executable import ExecutableAllocation, parse_executable_entry
from values import object_fields, rational, require_int


@dataclass(frozen=True)
class ValidatedStation:
    envelope: StationEnvelope
    roles: tuple[str, str]
    public_draws: tuple[str, ...]
    private_draw_count: int
    counts: tuple[EvidenceCount, ...]
    fingerprint: str
    allocations: tuple[ExecutableAllocation, ...] = ()


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


def _parse_allocations(raw_allocations, public_count, private_count):
    if not isinstance(raw_allocations, list):
        raise ValueError('executable station piece must list its allocations')
    if len(raw_allocations) > 1 << (public_count + private_count):
        raise ValueError('invalid executable allocation table size')
    seen_ids = set()
    seen_keys = set()
    allocations = []
    for raw in raw_allocations:
        allocation = parse_executable_entry(raw, public_count)
        if allocation.allocation_id in seen_ids:
            raise ValueError('duplicate executable allocation identity')
        seen_ids.add(allocation.allocation_id)
        key = (allocation.public_values, allocation.quota)
        seen_keys.add(key)
        allocations.append(allocation)
    if [item.allocation_id for item in allocations] != sorted(seen_ids):
        raise ValueError('executable allocation entries must be ordered by identity')
    return tuple(allocations)


def validate_station(wire):
    envelope = decode_envelope(wire)
    if envelope.version == ENVELOPE_V1:
        body_fields = ('roles', 'public_draws', 'private_draw_count', 'counts')
    else:
        body_fields = ('roles', 'public_draws', 'private_draw_count', 'allocations')
    raw = object_fields(json.loads(envelope.body), body_fields)
    roles = validate_roles(raw['roles'])
    if envelope.role not in roles:
        raise ValueError('issuing role is outside the protocol roles')
    public = draw_names(raw['public_draws'])
    private = require_int(raw['private_draw_count'], 'private draw count', 0)
    if list(public) != raw['public_draws'] or len(public) > 3 or len(public) + private > 6:
        raise ValueError('invalid public draw order or station draw count')
    fingerprint = content_fingerprint(envelope)
    if envelope.version == ENVELOPE_V1:
        counts = _parse_counts(raw['counts'], len(public), private)
        return ValidatedStation(envelope, roles, public, private, counts, fingerprint)
    allocations = _parse_allocations(raw['allocations'], len(public), private)
    return ValidatedStation(envelope, roles, public, private, (), fingerprint, allocations)
