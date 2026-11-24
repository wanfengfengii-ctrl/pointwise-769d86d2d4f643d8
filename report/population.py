from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from intake.pairing import ReceivedPair
from report.request import ReportRequest


@dataclass(frozen=True)
class WeightedAllocation:
    quota: int
    effect: Fraction
    count: int


def iter_conditioned_allocations(pair: ReceivedPair, request: ReportRequest):
    right_by_public = defaultdict(list)
    for right in pair.second.station.counts:
        right_by_public[right.public_values].append(right)
    for left in pair.first.station.counts:
        for right in right_by_public.get(left.public_values, ()):
            quota = left.quota + right.quota
            if request.quota_min <= quota <= request.quota_max:
                yield WeightedAllocation(quota, left.effect + right.effect, left.count * right.count)
