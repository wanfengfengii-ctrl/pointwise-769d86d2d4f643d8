from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from design.shared_draws import require_bit
from values import canonical_json, object_fields, require_int


@dataclass(frozen=True)
class LocalRule:
    when: tuple[tuple[str, int], ...]
    quota_min: int = 0
    quota_max: int | None = None
    forbid: bool = False

    def as_dict(self):
        return {'when': dict(self.when), 'quota_min': self.quota_min,
                'quota_max': self.quota_max, 'forbid': self.forbid}


def validate_local_rules(raw_rules, definitions):
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes, bytearray)):
        raise ValueError('station rules must be a sequence')
    names = {draw.name for draw in definitions}
    rules = []
    for raw in raw_rules:
        object_fields(raw, ('when',), ('quota_min', 'quota_max', 'forbid'))
        when = raw['when']
        if not isinstance(when, Mapping) or not when.keys() <= names:
            raise ValueError('local rule references an unknown draw')
        lower = require_int(raw.get('quota_min', 0), 'local quota minimum', 0)
        upper = raw.get('quota_max')
        if upper is not None:
            require_int(upper, 'local quota maximum', lower)
        forbid = raw.get('forbid', False)
        if type(forbid) is not bool or (forbid and (lower != 0 or upper is not None)):
            raise ValueError('invalid local prohibition')
        predicates = tuple(sorted((name, require_bit(value)) for name, value in when.items()))
        rules.append(LocalRule(predicates, lower, upper, forbid))
    return tuple(sorted(rules, key=lambda rule: canonical_json(rule.as_dict())))


def allows_local_allocation(rules, assignment, quota):
    for rule in rules:
        if all(assignment[name] == value for name, value in rule.when):
            if rule.forbid or quota < rule.quota_min:
                return False
            if rule.quota_max is not None and quota > rule.quota_max:
                return False
    return True
