import json

from issue.envelope import ENVELOPE_V2, decode_envelope
from storage import write_transaction
from values import canonical_json, require_name


def canonical_assignment(assignment):
    return canonical_json([[name, value] for name, value in assignment])


class IssueRegister:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS station_issues (
            issue_id TEXT PRIMARY KEY NOT NULL,
            revision_id INTEGER NOT NULL REFERENCES measurement_revisions(revision_id),
            wire BLOB NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS executable_allocations (
            issue_id TEXT NOT NULL,
            allocation_id TEXT NOT NULL,
            assignment TEXT NOT NULL,
            PRIMARY KEY (issue_id, allocation_id),
            FOREIGN KEY (issue_id) REFERENCES station_issues(issue_id)
        )''')

    def get_issue(self, issue_id):
        require_name(issue_id, 'issue id')
        row = self.db.execute('SELECT wire FROM station_issues WHERE issue_id = ?',
                              (issue_id,)).fetchone()
        return None if row is None else row[0]

    def save_issue(self, wire):
        envelope = decode_envelope(wire)
        with write_transaction(self.db):
            prior = self.get_issue(envelope.issue_id)
            if prior is None:
                self.db.execute('INSERT INTO station_issues VALUES (?, ?, ?)',
                                (envelope.issue_id, envelope.revision_id, wire))
            elif prior != wire:
                raise ValueError('issue id already binds different fixed evidence')
        return wire

    def save_executable_issue(self, wire, allocations):
        """Persist a version 2 issue together with its private assignment index."""
        envelope = decode_envelope(wire)
        if envelope.version != ENVELOPE_V2:
            raise ValueError('executable issue must use envelope version 2')
        with write_transaction(self.db):
            prior = self.get_issue(envelope.issue_id)
            if prior is None:
                self.db.execute('INSERT INTO station_issues VALUES (?, ?, ?)',
                                (envelope.issue_id, envelope.revision_id, wire))
            elif prior != wire:
                raise ValueError('issue id already binds different fixed evidence')
            for allocation in allocations:
                self.db.execute('''INSERT OR IGNORE INTO executable_allocations
                    (issue_id, allocation_id, assignment) VALUES (?, ?, ?)''',
                    (envelope.issue_id, allocation.allocation_id,
                     canonical_assignment(allocation.assignment)))
        return wire

    def get_assignment(self, issue_id, allocation_id):
        require_name(issue_id, 'issue id')
        require_name(allocation_id, 'allocation id')
        row = self.db.execute('''SELECT assignment FROM executable_allocations
            WHERE issue_id = ? AND allocation_id = ?''',
                              (issue_id, allocation_id)).fetchone()
        if row is None:
            return None
        return tuple((name, value) for name, value in json.loads(row[0]))
