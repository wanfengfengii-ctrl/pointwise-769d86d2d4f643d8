import json
import re
from dataclasses import dataclass
from hashlib import sha256

from storage import database_id
from values import canonical_json, object_fields, require_name


@dataclass(frozen=True)
class StationEnvelope:
    issue_id: str
    trial_id: str
    role: str
    protocol_id: str
    revision_id: int
    body: bytes


def _content(envelope):
    return {
        'version': 1,
        'identity': {
            'issue_id': envelope.issue_id,
            'trial_id': envelope.trial_id,
            'role': envelope.role,
            'protocol_id': envelope.protocol_id,
            'revision_id': envelope.revision_id,
        },
        'body': json.loads(envelope.body),
    }


def content_fingerprint(envelope):
    return sha256(canonical_json(_content(envelope)).encode('ascii')).hexdigest()


def encode_envelope(envelope):
    content = _content(envelope)
    content['fingerprint'] = content_fingerprint(envelope)
    return canonical_json(content).encode('ascii')


def decode_envelope(wire):
    if not isinstance(wire, bytes):
        raise ValueError('station envelope must be bytes')
    try:
        raw = json.loads(wire.decode('ascii'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('invalid station envelope encoding') from exc
    object_fields(raw, ('version', 'identity', 'body', 'fingerprint'))
    if type(raw['version']) is not int or raw['version'] != 1:
        raise ValueError('unsupported station envelope version')
    identity = object_fields(raw['identity'],
                             ('issue_id', 'trial_id', 'role', 'protocol_id', 'revision_id'))
    protocol_id = identity['protocol_id']
    if not isinstance(protocol_id, str) or not re.fullmatch('[0-9a-f]{64}', protocol_id):
        raise ValueError('invalid protocol fingerprint')
    envelope = StationEnvelope(
        require_name(identity['issue_id'], 'issue id'),
        require_name(identity['trial_id'], 'trial id'),
        require_name(identity['role'], 'station role'),
        protocol_id,
        database_id(identity['revision_id'], 'revision id'),
        canonical_json(raw['body']).encode('ascii'),
    )
    if wire != encode_envelope(envelope):
        raise ValueError('noncanonical station envelope or fingerprint mismatch')
    return envelope
