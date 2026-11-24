import json
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from report.request import ReportRequest, decode_report_request, encode_report_request
from report.tail import TailResult
from storage import database_id, write_transaction
from values import canonical_json, rational


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    request: ReportRequest
    result: TailResult


@dataclass(frozen=True)
class ReportReceipt:
    report_id: int
    token: str


def _encode_result(result):
    probability = None if result.probability is None else str(result.probability)
    return canonical_json({'tail_count': result.tail_count, 'eligible_count': result.eligible_count,
                           'probability': probability, 'status': result.status})


def _decode_result(payload):
    raw = json.loads(payload)
    if raw['probability'] is not None:
        raw['probability'] = rational(raw['probability'])
    return TailResult(**raw)


class ReportJournal:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY,
            first_receipt INTEGER NOT NULL REFERENCES station_receipts(receipt_id),
            second_receipt INTEGER NOT NULL REFERENCES station_receipts(receipt_id),
            request TEXT NOT NULL,
            result TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS report_receipts (
            report_id INTEGER PRIMARY KEY REFERENCES reports(report_id),
            token TEXT NOT NULL UNIQUE
        )''')

    def commit_report(self, request, result, *, before_commit: Callable[[], None] | None = None):
        with write_transaction(self.db):
            cursor = self.db.execute('''INSERT INTO reports
                (first_receipt, second_receipt, request, result) VALUES (?, ?, ?, ?)''',
                (*request.receipt_ids, encode_report_request(request), _encode_result(result)))
            record = ReportRecord(cursor.lastrowid, request, result)
            receipt = ReportReceipt(record.report_id, uuid4().hex)
            self.db.execute('INSERT INTO report_receipts VALUES (?, ?)',
                            (receipt.report_id, receipt.token))
            if before_commit is not None:
                before_commit()
        return record, receipt

    def load_report(self, report_id):
        database_id(report_id, 'report id')
        row = self.db.execute('''SELECT reports.first_receipt, reports.second_receipt,
                reports.request, reports.result, report_receipts.token
            FROM reports LEFT JOIN report_receipts USING (report_id)
            WHERE reports.report_id = ?''', (report_id,)).fetchone()
        if row is None:
            return None
        first, second, request_payload, result_payload, token = row
        request = decode_report_request(request_payload)
        if token is None or request.receipt_ids != (first, second):
            raise ValueError('report is missing its first receipt or has inconsistent parents')
        record = ReportRecord(report_id, request, _decode_result(result_payload))
        return record, ReportReceipt(report_id, token)
