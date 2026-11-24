from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256

from design.local_rules import LocalRule, validate_local_rules
from design.shared_draws import DrawDefinition, draw_names, validate_draw_definitions
from values import canonical_json, require_name


@dataclass(frozen=True)
class Protocol:
    trial_id: str
    roles: tuple[str, str]
    public_draws: tuple[str, ...]
    draws: tuple[tuple[DrawDefinition, ...], tuple[DrawDefinition, ...]]
    local_rules: tuple[tuple[LocalRule, ...], tuple[LocalRule, ...]]

    def role_index(self, role):
        if role not in self.roles:
            raise ValueError('unknown station role')
        return self.roles.index(role)

    def as_dict(self):
        return {
            'trial_id': self.trial_id,
            'roles': self.roles,
            'public_draws': self.public_draws,
            'private_draws': {
                role: tuple(draw.name for draw in self.draws[index] if not draw.shared)
                for index, role in enumerate(self.roles)
            },
            'local_rules': {
                role: tuple(rule.as_dict() for rule in self.local_rules[index])
                for index, role in enumerate(self.roles)
            },
        }

    @property
    def protocol_id(self):
        return sha256(canonical_json(self.as_dict()).encode('ascii')).hexdigest()


def validate_roles(roles):
    if (not isinstance(roles, Sequence) or isinstance(roles, (str, bytes, bytearray))
            or len(roles) != 2):
        raise ValueError('expected two ordered station roles')
    first, second = (require_name(role, 'station role') for role in roles)
    if first == second:
        raise ValueError('station roles must be distinct')
    return first, second


def _by_role(value, roles):
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not value.keys() <= set(roles):
        raise ValueError('station definitions reference an unknown role')
    return value


def build_protocol(trial_id, roles, public_draws, private_draws=None, local_rules=None):
    trial = require_name(trial_id, 'trial id')
    ordered_roles = validate_roles(roles)
    public = draw_names(public_draws)
    private_by_role = _by_role(private_draws, ordered_roles)
    rule_by_role = _by_role(local_rules, ordered_roles)
    definitions = tuple(validate_draw_definitions(public, private_by_role.get(role, ()))
                        for role in ordered_roles)
    rules = tuple(validate_local_rules(rule_by_role.get(role, ()), draws)
                  for role, draws in zip(ordered_roles, definitions))
    return Protocol(trial, ordered_roles, public, definitions, rules)
