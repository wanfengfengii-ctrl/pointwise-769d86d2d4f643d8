from collections.abc import Sequence
from dataclasses import dataclass

from intake.archive import ArchivedStation
from issue.envelope import ENVELOPE_V2


@dataclass(frozen=True)
class ExecutableStation:
    receipt_id: int
    issue_id: str
    fingerprint: str
    role: str
    public_draws: tuple[str, ...]
    allocations: tuple  # tuple of ExecutableAllocation


@dataclass(frozen=True)
class ExecutablePair:
    first: ExecutableStation
    second: ExecutableStation
    first_archived: ArchivedStation
    second_archived: ArchivedStation


def _executable_station(archived: ArchivedStation):
    station = archived.station
    if station.envelope.version != ENVELOPE_V2:
        raise ValueError('draw tickets require version 2 executable station pieces')
    return ExecutableStation(
        archived.receipt.receipt_id,
        station.envelope.issue_id,
        archived.receipt.fingerprint,
        station.envelope.role,
        station.public_draws,
        station.allocations,
    )


def resolve_executable_pair(archive, receipt_ids):
    if (not isinstance(receipt_ids, Sequence) or isinstance(receipt_ids, (str, bytes, bytearray))
            or len(receipt_ids) != 2):
        raise ValueError('expected two ordered station receipt ids')
    first_archived, second_archived = (archive.get_station(receipt_id) for receipt_id in receipt_ids)
    left, right = first_archived.station, second_archived.station
    if left.envelope.trial_id != right.envelope.trial_id:
        raise ValueError('station evidence comes from different trials')
    if (left.envelope.protocol_id != right.envelope.protocol_id
            or left.roles != right.roles or left.public_draws != right.public_draws):
        raise ValueError('station evidence follows different protocols')
    if (left.envelope.role, right.envelope.role) != left.roles:
        raise ValueError('station evidence is outside the required role order')
    first, second = _executable_station(first_archived), _executable_station(second_archived)
    if first.issue_id == second.issue_id:
        raise ValueError('both station pieces claim the same issue identity')
    return ExecutablePair(first, second, first_archived, second_archived)
