from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from report.population import WeightedAllocation
from values import rational, require_int


@dataclass(frozen=True)
class TailResult:
    tail_count: int
    eligible_count: int
    probability: Fraction | None
    status: str

    def __post_init__(self):
        require_int(self.tail_count, 'tail count', 0)
        require_int(self.eligible_count, 'eligible count', self.tail_count)
        if self.eligible_count == 0:
            if self.status != 'no_eligible_allocations' or self.probability is not None:
                raise ValueError('empty conditional population has no probability')
        elif (self.status != 'calculated' or not isinstance(self.probability, Fraction)
              or self.probability != Fraction(self.tail_count, self.eligible_count)):
            raise ValueError('tail probability disagrees with the counts')


def calculate_tail(allocations: Iterable[WeightedAllocation], threshold):
    cutoff = rational(threshold)
    eligible = 0
    tail = 0
    for allocation in allocations:
        weight = require_int(allocation.count, 'allocation multiplicity', 1)
        eligible += weight
        if allocation.effect >= cutoff:
            tail += weight
    if eligible == 0:
        return TailResult(0, 0, None, 'no_eligible_allocations')
    return TailResult(tail, eligible, Fraction(tail, eligible), 'calculated')
