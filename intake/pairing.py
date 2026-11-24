from collections.abc import Sequence
from dataclasses import dataclass

from intake.archive import ArchivedStation


@dataclass(frozen=True)
class ReceivedPair:
    first: ArchivedStation
    second: ArchivedStation


def resolve_pair(archive, receipt_ids):
    if (not isinstance(receipt_ids, Sequence) or isinstance(receipt_ids, (str, bytes, bytearray))
            or len(receipt_ids) != 2):
        raise ValueError('expected two ordered station receipt ids')
    first, second = (archive.get_station(receipt_id) for receipt_id in receipt_ids)
    left = first.station
    right = second.station
    if left.envelope.trial_id != right.envelope.trial_id:
        raise ValueError('station evidence comes from different trials')
    if (left.envelope.protocol_id != right.envelope.protocol_id
            or left.roles != right.roles or left.public_draws != right.public_draws):
        raise ValueError('station evidence follows different protocols')
    if (left.envelope.role, right.envelope.role) != left.roles:
        raise ValueError('station evidence is outside the required role order')
    return ReceivedPair(first, second)
