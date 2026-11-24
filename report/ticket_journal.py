from collections.abc import Callable

from storage import write_transaction
from values import canonical_json, require_int


def parse_window(quota_min, quota_max):
    lower = require_int(quota_min, 'ticket quota minimum')
    upper = require_int(quota_max, 'ticket quota maximum', lower)
    return lower, upper


def parent_entry(archived):
    receipt = archived.receipt
    return {'receipt_id': receipt.receipt_id,
            'issue_id': receipt.issue_id,
            'fingerprint': receipt.fingerprint}


class TicketJournal:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY,
            initial_ticket_id INTEGER REFERENCES tickets(ticket_id),
            payload TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS ticket_reissues (
            initial_ticket_id INTEGER PRIMARY KEY REFERENCES tickets(ticket_id),
            reissue_ticket_id INTEGER NOT NULL UNIQUE REFERENCES tickets(ticket_id),
            quota_min INTEGER NOT NULL,
            quota_max INTEGER NOT NULL,
            kept INTEGER NOT NULL
        )''')

    def get_ticket_payload(self, ticket_id):
        row = self.db.execute('SELECT payload FROM tickets WHERE ticket_id = ?',
                              (ticket_id,)).fetchone()
        return None if row is None else row[0]

    def get_reissue(self, initial_ticket_id):
        row = self.db.execute('''SELECT reissue_ticket_id, quota_min, quota_max
            FROM ticket_reissues WHERE initial_ticket_id = ?''',
                              (initial_ticket_id,)).fetchone()
        return None if row is None else row

    def commit_ticket(self, ticket, *, before_commit: Callable[[], None] | None = None):
        payload = canonical_json(ticket)
        with write_transaction(self.db):
            cursor = self.db.execute(
                'INSERT INTO tickets (initial_ticket_id, payload) VALUES (?, ?)',
                (ticket['initial_ticket_id'], payload))
            ticket_id = cursor.lastrowid
            if ticket['initial_ticket_id'] is not None:
                self.db.execute('''INSERT INTO ticket_reissues
                    (initial_ticket_id, reissue_ticket_id, quota_min, quota_max, kept)
                    VALUES (?, ?, ?, ?, ?)''',
                    (ticket['initial_ticket_id'], ticket_id, ticket['quota_min'],
                     ticket['quota_max'], 1 if ticket['kept'] else 0))
            if before_commit is not None:
                before_commit()
        return ticket_id
