from dataclasses import dataclass

from design.local_rules import allows_local_allocation
from design.shared_draws import validate_assignment
from measure.contrasts import StationTotals, sum_station_contributions


@dataclass(frozen=True)
class StationReview:
    revision_id: int
    assignment: tuple[tuple[str, int], ...]
    allowed: bool
    totals: StationTotals


def audit_allocation(revision, assignment):
    protocol = revision.protocol
    index = protocol.role_index(revision.role)
    values = validate_assignment(protocol.draws[index], assignment)
    totals = sum_station_contributions(revision.rows, values)
    allowed = allows_local_allocation(protocol.local_rules[index], values, totals.quota)
    return StationReview(revision.revision_id, tuple(values.items()), allowed, totals)


def review_station(store, revision_id, assignment):
    return audit_allocation(store.get_revision(revision_id), assignment)
