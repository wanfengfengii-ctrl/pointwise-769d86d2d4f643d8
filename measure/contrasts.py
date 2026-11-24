from dataclasses import dataclass
from fractions import Fraction

from measure.provenance import SourceReference


@dataclass(frozen=True)
class RowContribution:
    source: SourceReference
    draw: str
    value: int
    quota: int
    effect: Fraction


@dataclass(frozen=True)
class StationTotals:
    quota: int
    effect: Fraction
    contributions: tuple[RowContribution, ...]


def measure_row_contribution(row, assignment):
    value = assignment[row.draw]
    reading = row.choices[value]
    return RowContribution(row.source, row.draw, value, reading.quota,
                           reading.treated - reading.control)


def sum_station_contributions(rows, assignment):
    contributions = tuple(measure_row_contribution(row, assignment) for row in rows)
    quota = sum(item.quota for item in contributions)
    effect = sum((item.effect for item in contributions), Fraction(0))
    return StationTotals(quota, effect, contributions)
