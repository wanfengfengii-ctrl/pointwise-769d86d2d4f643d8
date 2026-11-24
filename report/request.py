import json
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from storage import database_id
from values import canonical_json, object_fields, rational, require_int


@dataclass(frozen=True)
class ReportRequest:
    receipt_ids: tuple[int, int]
    quota_min: int
    quota_max: int
    threshold: Fraction


def parse_report_request(receipt_ids, quota_min, quota_max, threshold):
    if (not isinstance(receipt_ids, Sequence) or isinstance(receipt_ids, (str, bytes, bytearray))
            or len(receipt_ids) != 2):
        raise ValueError('expected two ordered station receipt ids')
    parents = tuple(database_id(value, 'station receipt id') for value in receipt_ids)
    lower = require_int(quota_min, 'report quota minimum')
    upper = require_int(quota_max, 'report quota maximum', lower)
    return ReportRequest(parents, lower, upper, rational(threshold))


def encode_report_request(request):
    return canonical_json({'receipt_ids': request.receipt_ids, 'quota_min': request.quota_min,
                           'quota_max': request.quota_max, 'threshold': str(request.threshold)})


def decode_report_request(payload):
    raw = object_fields(json.loads(payload), ('receipt_ids', 'quota_min', 'quota_max', 'threshold'))
    return parse_report_request(**raw)
