from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from values import require_name


@dataclass(frozen=True)
class DrawDefinition:
    name: str
    shared: bool


def draw_names(names):
    if not isinstance(names, Sequence) or isinstance(names, (str, bytes, bytearray)):
        raise ValueError('draw names must be a sequence')
    normalized = tuple(require_name(name, 'draw name') for name in names)
    if len(set(normalized)) != len(normalized):
        raise ValueError('duplicate draw name')
    return tuple(sorted(normalized))


def validate_draw_definitions(public_names, private_names):
    public = draw_names(public_names)
    private = draw_names(private_names)
    if len(public) > 3 or len(public) + len(private) > 6:
        raise ValueError('too many draws for one station')
    if set(public).intersection(private):
        raise ValueError('a draw cannot be public and private at the same station')
    return (tuple(DrawDefinition(name, True) for name in public)
            + tuple(DrawDefinition(name, False) for name in private))


def require_bit(value):
    if type(value) is not int or value not in (0, 1):
        raise ValueError('draw values must be integer 0 or 1')
    return value


def validate_assignment(definitions, assignment):
    names = tuple(draw.name for draw in definitions)
    if not isinstance(assignment, Mapping) or assignment.keys() != set(names):
        raise ValueError('assignment must provide exactly the station draws')
    return {name: require_bit(assignment[name]) for name in names}


def public_draw_values(definitions, assignment):
    return tuple(assignment[draw.name] for draw in definitions if draw.shared)
