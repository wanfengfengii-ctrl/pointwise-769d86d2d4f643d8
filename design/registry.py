import json

from design.protocol import build_protocol
from storage import write_transaction
from values import canonical_json, require_name


class ProtocolRegistry:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS protocols (
            trial_id TEXT PRIMARY KEY NOT NULL,
            definition TEXT NOT NULL
        )''')

    def get_protocol(self, trial_id):
        require_name(trial_id, 'trial id')
        row = self.db.execute('SELECT definition FROM protocols WHERE trial_id = ?',
                              (trial_id,)).fetchone()
        if row is None:
            raise KeyError(f'unknown trial {trial_id}')
        return build_protocol(**json.loads(row[0]))

    def save_protocol(self, protocol):
        definition = canonical_json(protocol.as_dict())
        with write_transaction(self.db):
            prior = self.db.execute('SELECT definition FROM protocols WHERE trial_id = ?',
                                    (protocol.trial_id,)).fetchone()
            if prior is None:
                self.db.execute('INSERT INTO protocols VALUES (?, ?)',
                                (protocol.trial_id, definition))
            elif prior[0] != definition:
                raise ValueError('trial already has a different protocol')
        return protocol


def register_protocol(registry, trial_id, roles, public_draws, private_draws=None, local_rules=None):
    protocol = build_protocol(trial_id, roles, public_draws, private_draws, local_rules)
    return registry.save_protocol(protocol)
