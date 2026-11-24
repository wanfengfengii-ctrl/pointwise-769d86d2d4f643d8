from issue.envelope import StationEnvelope, decode_envelope, encode_envelope
from issue.evidence import build_station_evidence
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
