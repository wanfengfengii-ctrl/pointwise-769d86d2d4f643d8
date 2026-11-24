from dataclasses import dataclass

from intake.executable_pairing import ExecutablePair


@dataclass(frozen=True)
class CompleteAllocation:
    """One complete allocation: both stations admitted, same public values, quota in window."""

    left: object
    right: object

    @property
    def quota(self):
        return self.left.quota + self.right.quota

    @property
    def public_values(self):
        return self.left.public_values

    def key(self):
        return self.left.allocation_id, self.right.allocation_id


def enumerate_complete_allocations(pair: ExecutablePair, quota_min, quota_max):
    right_by_public = {}
    for right in pair.second.allocations:
        right_by_public.setdefault(right.public_values, []).append(right)
    complete = []
    for left in pair.first.allocations:
        for right in right_by_public.get(left.public_values, ()):
            quota = left.quota + right.quota
            if quota_min <= quota <= quota_max:
                complete.append(CompleteAllocation(left, right))
    # A fixed, canonical order keeps the uniform draw independent of insertion order.
    complete.sort(key=lambda item: item.key())
    return tuple(complete)


def find_complete_allocation(population, left_id, right_id):
    target = (left_id, right_id)
    for complete in population:
        if complete.key() == target:
            return complete
    return None
