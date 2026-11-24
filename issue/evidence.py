from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from design.shared_draws import public_draw_values
from measure.local_review import audit_allocation


@dataclass(frozen=True, order=True)
class EvidenceCount:
    public_values: tuple[int, ...]
    quota: int
    effect: Fraction
    count: int

    def as_dict(self):
        return {'public_values': self.public_values, 'quota': self.quota,
                'effect': str(self.effect), 'count': self.count}


def build_station_evidence(revision):
    index = revision.protocol.role_index(revision.role)
    definitions = revision.protocol.draws[index]
    names = tuple(draw.name for draw in definitions)
    counts = Counter()
    for values in product((0, 1), repeat=len(names)):
        assignment = dict(zip(names, values))
        review = audit_allocation(revision, assignment)
        if review.allowed:
            key = (public_draw_values(definitions, assignment), review.totals.quota,
                   review.totals.effect)
            counts[key] += 1
    return tuple(EvidenceCount(*key, counts[key]) for key in sorted(counts))
