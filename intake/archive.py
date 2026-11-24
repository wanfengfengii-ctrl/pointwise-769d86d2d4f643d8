from dataclasses import dataclass

from intake.receipts import StationReceipt, decode_receipt, encode_receipt, make_first_receipt
from intake.validate import ValidatedStation, validate_station
from storage import database_id, write_transaction


@dataclass(frozen=True)
class ArchivedStation:
    receipt: StationReceipt
    station: ValidatedStation
    wire: bytes


class IntakeArchive:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS station_archive (
            receipt_id INTEGER PRIMARY KEY,
            issue_id TEXT NOT NULL UNIQUE,
            wire BLOB NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS station_receipts (
            receipt_id INTEGER PRIMARY KEY REFERENCES station_archive(receipt_id),
            body TEXT NOT NULL
        )''')

    def put_station(self, wire):
        station = validate_station(wire)
        issue_id = station.envelope.issue_id
        with write_transaction(self.db):
            prior = self.db.execute('''SELECT receipt_id, wire FROM station_archive
                WHERE issue_id = ?''', (issue_id,)).fetchone()
            if prior is not None:
                if prior[1] != wire:
                    raise ValueError('received issue id already binds different bytes')
                receipt = self.get_receipt(prior[0])
            else:
                cursor = self.db.execute('INSERT INTO station_archive (issue_id, wire) VALUES (?, ?)',
                                         (issue_id, wire))
                receipt = make_first_receipt(cursor.lastrowid, station)
                self.db.execute('INSERT INTO station_receipts VALUES (?, ?)',
                                (receipt.receipt_id, encode_receipt(receipt)))
        return receipt

    def get_receipt(self, receipt_id):
        database_id(receipt_id, 'station receipt id')
        row = self.db.execute('SELECT body FROM station_receipts WHERE receipt_id = ?',
                              (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(f'unknown station receipt {receipt_id}')
        return decode_receipt(row[0])

    def get_station(self, receipt_id):
        receipt = self.get_receipt(receipt_id)
        row = self.db.execute('SELECT issue_id, wire FROM station_archive WHERE receipt_id = ?',
                              (receipt_id,)).fetchone()
        if row is None:
            raise ValueError('station receipt is missing its archived evidence')
        issue_id, wire = row
        station = validate_station(wire)
        if (receipt.receipt_id != receipt_id or receipt.issue_id != issue_id
                or station.envelope.issue_id != issue_id or receipt.fingerprint != station.fingerprint):
            raise ValueError('archive and first receipt identities disagree')
        return ArchivedStation(receipt, station, wire)
