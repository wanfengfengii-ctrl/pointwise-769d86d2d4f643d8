"""Exact uniform reissue with maximal whole-ticket retention.

The initial draw is uniform over the old-window population ``O`` (size ``m``)
and the reissue must be exactly uniform over the new-window population ``N``
(size ``n``). Maximising the probability that both stations keep their
original local allocation is the standard maximal coupling of the two uniform
distributions. With ``k`` shared allocations its coefficient is

    alpha = sum_y min(p(y), q(y)) = k / max(m, n),

which equals the mandated retention rate ``1/3`` for the main example
(``m = 4``, ``n = 6``, ``k = 2``).

On rejection the residual measures are sampled with exact integer weights so
that only ``randbelow`` callbacks provide randomness. The ``kept`` flag is true
exactly when the coupling selects the initial allocation.
"""
from report.executable_population import find_complete_allocation


def require_randbelow(randbelow):
    if not callable(randbelow):
        raise ValueError('randbelow must be callable')
    return randbelow


def _draw_index(randbelow, size):
    index = randbelow(size)
    if type(index) is not int or not 0 <= index < size:
        raise ValueError('randbelow returned a value outside [0, n)')
    return index


def _weighted_choice(randbelow, items, weights):
    total = sum(weights)
    if total <= 0:
        raise ValueError('empty residual distribution')
    pick = _draw_index(randbelow, total)
    running = 0
    for item, weight in zip(items, weights):
        running += weight
        if pick < running:
            return item
    raise RuntimeError('weighted choice exhausted its weights')


def _split_support(new_population, old_keys):
    shared = []
    new_only = []
    for allocation in new_population:
        if allocation.key() in old_keys:
            shared.append(allocation)
        else:
            new_only.append(allocation)
    return tuple(shared), tuple(new_only)


def reissue_choice(randbelow, old_population, new_population, initial):
    """Return ``(selected_complete_allocation, kept)``."""
    m = len(old_population)
    n = len(new_population)
    old_keys = {allocation.key() for allocation in old_population}
    shared, new_only = _split_support(new_population, old_keys)
    k = len(shared)
    retained = find_complete_allocation(
        new_population, initial.left.allocation_id, initial.right.allocation_id)
    if n >= m:
        # Acceptance probability alpha = k/n. A shared initial allocation is
        # retained with conditional probability m/n; on rejection the residual
        # measure q' has zero mass on the shared points and is uniform over the
        # n - k new-only allocations. When n > m the new-only set is always
        # nonempty because k <= m < n.
        if retained is not None and _draw_index(randbelow, n) < m:
            return retained, True
        if new_only:
            return new_only[_draw_index(randbelow, n - k)], False
        # Identical supports (n == m and every point shared): rejection lands
        # uniformly on the n - 1 allocations other than the retained one. An
        # initial draw outside N cannot occur here because N is a subset of O
        # and they have the same size.
        others = tuple(item for item in new_population if item.key() != retained.key())
        return others[_draw_index(randbelow, len(others))], False
    # n < m: shared allocations are always retained (their old mass is the
    # minimum). An initial draw outside N is coupled to the weighted residual:
    # shared points carry integer weight m - n, new-only points weight m,
    # total integer weight m(n - 1) over the n - 1 residual-eligible points.
    if retained is not None:
        return retained, True
    items = list(shared) + list(new_only)
    weights = [m - n] * len(shared) + [m] * len(new_only)
    return _weighted_choice(randbelow, tuple(items), tuple(weights)), False
