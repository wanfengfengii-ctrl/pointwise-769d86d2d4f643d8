import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from design.registry import register_protocol
from intake.archive import IntakeArchive
from intake.receive import receive_station
from issue.freeze import freeze_station
from issue.register import IssueRegister
from measure.imports import RevisionInput, record_revision
from measure.local_review import review_station
from measure.revisions import RevisionStore
from report.history import get_report
from report.journal import ReportJournal
from report.publish import publish_report
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


if __name__ == '__main__':
    main()
