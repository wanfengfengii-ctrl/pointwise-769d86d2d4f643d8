from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from values import object_fields, rational, require_int, require_name


@dataclass(frozen=True)
class SourceReference:
    record: str
    segment: str


@dataclass(frozen=True)
class Reading:
    treated: Fraction
    control: Fraction
    quota: int


@dataclass(frozen=True)
class MeasurementRow:
    source: SourceReference
    draw: str
    choices: tuple[Reading, Reading]

    def as_dict(self):
        return {
            'source': {'record': self.source.record, 'segment': self.source.segment},
            'draw': self.draw,
            'choices': [{'treated': str(reading.treated), 'control': str(reading.control),
                         'quota': reading.quota} for reading in self.choices],
        }


def validate_source_reference(raw):
    object_fields(raw, ('record', 'segment'))
    return SourceReference(require_name(raw['record'], 'source record'),
                           require_name(raw['segment'], 'source segment'))


def measurement_row_key(row):
    return row.source.record, row.source.segment


def _parse_reading(raw):
    object_fields(raw, ('treated', 'control', 'quota'))
    return Reading(rational(raw['treated']), rational(raw['control']),
                   require_int(raw['quota'], 'measured quota', 0))


def parse_measurement_row(raw):
    object_fields(raw, ('source', 'draw', 'choices'))
    source = validate_source_reference(raw['source'])
    draw = require_name(raw['draw'], 'measurement draw')
    choices = raw['choices']
    if (not isinstance(choices, Sequence) or isinstance(choices, (str, bytes, bytearray))
            or len(choices) != 2):
        raise ValueError('expected one reading group for each draw value')
    return MeasurementRow(source, draw, (_parse_reading(choices[0]), _parse_reading(choices[1])))
