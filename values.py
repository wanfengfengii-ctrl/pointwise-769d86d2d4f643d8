import json
import re
from collections.abc import Mapping
from fractions import Fraction


_RATIONAL = re.compile(r'[+-]?[0-9]+(?:/[0-9]+)?')


def require_name(value, label):
    if not isinstance(value, str) or not value or value != value.strip() or '\x00' in value:
        raise ValueError(f'{label} must be a nonempty identifier')
    return value


def require_int(value, label, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f'{label} is outside its integer domain')
    return value


def rational(value):
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str) and _RATIONAL.fullmatch(value):
        try:
            return Fraction(value)
        except (ZeroDivisionError, ValueError) as exc:
            raise ValueError('invalid rational number') from exc
    raise ValueError('expected an integer or an exact rational number')


def object_fields(value, required, optional=()):
    required = set(required)
    if not isinstance(value, Mapping) or not required <= value.keys():
        raise ValueError('missing object fields')
    if value.keys() - required - set(optional):
        raise ValueError('unexpected object fields')
    return value


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
