from dataclasses import dataclass
from itertools import product
from uuid import uuid4

from design.shared_draws import public_draw_values, require_bit
from measure.local_review import audit_allocation
from values import canonical_json, object_fields, require_int, require_name


@dataclass(frozen=True)
class ExecutableAllocation:
    """One redeemable local allocation inside a version 2 station piece.

    ``allocation_id`` is an opaque handle: its ordering and value never encode
    private draw names or private draw values, which stay at the issuing site.
    """

    allocation_id: str
    public_values: tuple[int, ...]
    quota: int
    assignment: tuple[tuple[str, int], ...]

    def as_body_entry(self):
        return {'allocation_id': self.allocation_id,
                'public_values': list(self.public_values),
                'quota': self.quota}


def parse_executable_entry(raw, public_count):
    object_fields(raw, ('allocation_id', 'public_values', 'quota'))
    allocation_id = require_name(raw['allocation_id'], 'executable allocation id')
    values = raw['public_values']
    if not isinstance(values, list) or len(values) != public_count:
        raise ValueError('wrong number of public values in executable allocation')
    public_values = tuple(require_bit(value) for value in values)
    quota = require_int(raw['quota'], 'executable allocation quota', 0)
    return ExecutableAllocation(allocation_id, public_values, quota, ())


def build_executable_allocations(revision):
    """Enumerate every admissible local allocation with a distinct identity."""
    index = revision.protocol.role_index(revision.role)
    definitions = revision.protocol.draws[index]
    names = tuple(draw.name for draw in definitions)
    allocations = []
    for values in product((0, 1), repeat=len(names)):
        assignment = dict(zip(names, values))
        review = audit_allocation(revision, assignment)
        if review.allowed:
            allocations.append(ExecutableAllocation(
                uuid4().hex,
                public_draw_values(definitions, assignment),
                review.totals.quota,
                tuple(assignment.items()),
            ))
    # The body order follows the opaque random identity, never the private bits.
    return tuple(sorted(allocations, key=lambda item: item.allocation_id))


def encode_segment(issue_id, allocation_id):
    return canonical_json({'issue_id': issue_id, 'allocation_id': allocation_id})


def decode_segment(segment):
    if isinstance(segment, (str, bytes, bytearray)):
        raise ValueError('station ticket segment must be a decoded JSON object')
    raw = object_fields(segment, ('issue_id', 'allocation_id'))
    return (require_name(raw['issue_id'], 'segment issue id'),
            require_name(raw['allocation_id'], 'segment allocation id'))
