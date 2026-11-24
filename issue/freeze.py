from issue.envelope import ENVELOPE_V2, StationEnvelope, decode_envelope, encode_envelope
from issue.evidence import build_station_evidence
from issue.executable import (
    build_executable_allocations,
    decode_segment,
)
from measure.local_review import audit_allocation
from values import canonical_json


def freeze_station(revisions, issues, revision_id, issue_id):
    if revisions.db is not issues.db:
        raise ValueError('revision and issue stores must use the same station connection')
    revision = revisions.get_revision(revision_id)
    prior = issues.get_issue(issue_id)
    if prior is not None:
        if decode_envelope(prior).revision_id != revision_id:
            raise ValueError('issue id already binds another revision')
        return prior
    protocol = revision.protocol
    draws = protocol.draws[protocol.role_index(revision.role)]
    body = {
        'roles': protocol.roles,
        'public_draws': protocol.public_draws,
        'private_draw_count': sum(not draw.shared for draw in draws),
        'counts': [item.as_dict() for item in build_station_evidence(revision)],
    }
    envelope = StationEnvelope(issue_id, protocol.trial_id, revision.role,
                               protocol.protocol_id, revision_id,
                               canonical_json(body).encode('ascii'))
    return issues.save_issue(encode_envelope(envelope))


def _executable_body(protocol, role, allocations):
    draws = protocol.draws[protocol.role_index(role)]
    return {
        'roles': protocol.roles,
        'public_draws': protocol.public_draws,
        'private_draw_count': sum(not draw.shared for draw in draws),
        'allocations': [item.as_body_entry() for item in allocations],
    }


def freeze_executable_station(revisions, issues, revision_id, issue_id):
    """Freeze a version 2 station piece with distinct redeemable identities."""
    if revisions.db is not issues.db:
        raise ValueError('revision and issue stores must use the same station connection')
    revision = revisions.get_revision(revision_id)
    prior = issues.get_issue(issue_id)
    if prior is not None:
        envelope = decode_envelope(prior)
        if envelope.version != ENVELOPE_V2:
            raise ValueError('issue id already binds a version 1 station piece')
        if envelope.revision_id != revision_id:
            raise ValueError('issue id already binds another revision')
        return prior
    protocol = revision.protocol
    allocations = build_executable_allocations(revision)
    body = _executable_body(protocol, revision.role, allocations)
    envelope = StationEnvelope(issue_id, protocol.trial_id, revision.role,
                               protocol.protocol_id, revision_id,
                               canonical_json(body).encode('ascii'), ENVELOPE_V2)
    wire = encode_envelope(envelope)
    return issues.save_executable_issue(wire, allocations)


def redeem_station_ticket(revisions, issues, issue_id, segment):
    """Redeem a ticket segment independently against this station's own library."""
    if revisions.db is not issues.db:
        raise ValueError('revision and issue stores must use the same station connection')
    segment_issue_id, allocation_id = decode_segment(segment)
    wire = issues.get_issue(segment_issue_id)
    if wire is None:
        raise KeyError(f'unknown station issue {segment_issue_id}')
    envelope = decode_envelope(wire)
    if envelope.version != ENVELOPE_V2:
        raise ValueError('version 1 station pieces carry no executable ticket segment')
    if envelope.issue_id != issue_id:
        raise ValueError('ticket segment belongs to another station issue')
    assignment = issues.get_assignment(envelope.issue_id, allocation_id)
    if assignment is None:
        raise ValueError('ticket segment is not part of this station issue')
    revision = revisions.get_revision(envelope.revision_id)
    if revision.role != envelope.role:
        raise ValueError('ticket segment role does not match the issuing station')
    return audit_allocation(revision, dict(assignment))
