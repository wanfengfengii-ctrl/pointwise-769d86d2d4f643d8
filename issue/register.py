from issue.envelope import decode_envelope
from storage import write_transaction
from values import require_name


class IssueRegister:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS station_issues (
            issue_id TEXT PRIMARY KEY NOT NULL,
            revision_id INTEGER NOT NULL REFERENCES measurement_revisions(revision_id),
            wire BLOB NOT NULL
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
