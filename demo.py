import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from design.registry import register_protocol
from examples.quota_reissue import MAIN_PROTOCOL, MAIN_ROWS, ROLES
from intake.archive import IntakeArchive
from intake.receive import receive_station
from issue.freeze import freeze_executable_station, freeze_station, redeem_station_ticket
from issue.register import IssueRegister
from measure.imports import RevisionInput, record_revision
from measure.local_review import review_station
from measure.revisions import RevisionStore
from report.history import get_report
from report.journal import ReportJournal
from report.publish import publish_report
from report.ticket_history import get_ticket
from report.ticket_journal import TicketJournal
from report.ticket_publish import draw_ticket, reissue_ticket
from storage import open_database


def read_example(name):
    example_dir = Path(__file__).resolve().parent / 'examples'
    return json.loads((example_dir / name).read_text(encoding='utf-8'))


def describe(record):
    result = record.result
    return {
        'report_id': record.report_id,
        'parents': record.request.receipt_ids,
        'eligible': result.eligible_count,
        'tail': result.tail_count,
        'probability': None if result.probability is None else str(result.probability),
        'status': result.status,
    }


def quota_reissue_demo(root):
    """Exercise the executable station pieces and the quota reissue flow."""
    center_path = root / 'quota-center.sqlite'
    stores = {}
    with open_database(center_path) as center:
        archive = IntakeArchive(center)
        journal = TicketJournal(center)
        receipt_ids = []
        with ExitStack() as stack:
            for role in ROLES:
                db = stack.enter_context(open_database(root / f'quota-{role}.sqlite'))
                revisions = RevisionStore(db)
                issues = IssueRegister(db)
                register_protocol(revisions.registry, **MAIN_PROTOCOL)
                revision = record_revision(
                    revisions, RevisionInput(MAIN_PROTOCOL['trial_id'], role, MAIN_ROWS[role]))
                wire = freeze_executable_station(revisions, issues, revision.revision_id,
                                                 f'quota-{role}')
                receipt = receive_station(archive, wire)
                stores[role] = (revisions, issues)
                receipt_ids.append(receipt.receipt_id)
        # The station libraries are closed from here on; the center works alone.
        initial = draw_ticket(archive, journal, tuple(receipt_ids), 0, 1, _UniformRandbelow(11))
        print(json.dumps({'stage': 'initial_ticket', 'ticket_id': initial['ticket_id'],
                          'window': [initial['quota_min'], initial['quota_max']],
                          'segments': initial['segments']}, sort_keys=True))
        reissued = reissue_ticket(archive, journal, initial['ticket_id'],
                                  1, 3, _UniformRandbelow(23))
        print(json.dumps({'stage': 'reissued_ticket', 'ticket_id': reissued['ticket_id'],
                          'initial_ticket_id': reissued['initial_ticket_id'],
                          'window': [reissued['quota_min'], reissued['quota_max']],
                          'kept': reissued['kept']}, sort_keys=True))
        empty = reissue_ticket(archive, journal,
                               draw_ticket(archive, journal, tuple(receipt_ids),
                                           0, 1, _UniformRandbelow(31))['ticket_id'],
                               4, 4, _UniformRandbelow(37))
        print(json.dumps({'stage': 'empty_population', 'ticket_id': empty['ticket_id'],
                          'segments': empty['segments'], 'kept': empty['kept']}, sort_keys=True))
    with open_database(center_path) as center:
        history = get_ticket(IntakeArchive(center), TicketJournal(center), reissued['ticket_id'])
        print(json.dumps({'stage': 'reopen_center', 'retrieved_ticket': history['ticket_id'],
                          'matches_reissue': history == reissued}, sort_keys=True))
    # Each station independently redeems its own segment against its own library.
    with ExitStack() as stack:
        for index, role in enumerate(ROLES):
            db = stack.enter_context(open_database(root / f'quota-{role}.sqlite'))
            review = redeem_station_ticket(RevisionStore(db), IssueRegister(db),
                                           f'quota-{role}', reissued['segments'][index])
            print(json.dumps({'stage': 'station_redeem', 'station': role,
                              'allowed': review.allowed, 'quota': review.totals.quota,
                              'revision_id': review.revision_id}, sort_keys=True))


class _UniformRandbelow:
    def __init__(self, seed):
        import random
        self.random = random.Random(seed)

    def __call__(self, upper):
        return self.random.randrange(upper)


def main():
    design = read_example('protocol.json')
    measurements = read_example('measurements.json')
    trial_id = design['trial_id']
    left_role, right_role = design['roles']
    with TemporaryDirectory(prefix='strip-review-') as directory:
        root = Path(directory)
        center_path = root / 'center.sqlite'
        with open_database(center_path) as center:
            archive = IntakeArchive(center)
            journal = ReportJournal(center)
            with ExitStack() as sites:
                received = {}
                for role in design['roles']:
                    db = sites.enter_context(open_database(root / f'{role}.sqlite'))
                    revisions = RevisionStore(db)
                    issues = IssueRegister(db)
                    register_protocol(revisions.registry, **design)
                    revision = record_revision(revisions, RevisionInput(trial_id, role, measurements['initial'][role]))
                    values = {'U': 1} if role == left_role else {'U': 1, 'V': 0}
                    audit = review_station(revisions, revision.revision_id, values)
                    print(json.dumps({'station': role, 'allowed': audit.allowed,
                                      'quota': audit.totals.quota, 'effect': str(audit.totals.effect)}, sort_keys=True))
                    wire = freeze_station(revisions, issues, revision.revision_id, f'{role}-initial')
                    received[role] = receive_station(archive, wire)
                    if role == right_role:
                        correction = RevisionInput(trial_id, role, measurements['correction'], revision.revision_id)
                        corrected = record_revision(revisions, correction)
                        corrected_wire = freeze_station(revisions, issues, corrected.revision_id, f'{role}-corrected')
                        corrected_receipt = receive_station(archive, corrected_wire)
            left_id = received[left_role].receipt_id
            initial_pair = (left_id, received[right_role].receipt_id)
            corrected_pair = (left_id, corrected_receipt.receipt_id)
            initial, first_receipt = publish_report(archive, journal, initial_pair, 0, 1, 2)
            revised, _ = publish_report(archive, journal, corrected_pair, 0, 1, 2)
            empty, _ = publish_report(archive, journal, corrected_pair, 3, 3, 2)
            for record in (initial, revised, empty):
                print(json.dumps(describe(record), sort_keys=True))
        with open_database(center_path) as center:
            history = get_report(IntakeArchive(center), ReportJournal(center), initial.report_id)
            if history is None or history.record != initial or history.receipt != first_receipt:
                raise RuntimeError('original report or first receipt could not be retrieved')
            print(json.dumps({'retrieved': describe(history.record),
                              'parent_issues': [parent.receipt.issue_id for parent in history.parents]}, sort_keys=True))
        quota_reissue_demo(root)


if __name__ == '__main__':
    main()
