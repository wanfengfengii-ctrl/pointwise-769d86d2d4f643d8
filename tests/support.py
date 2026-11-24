import unittest
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import read_example
from design.registry import register_protocol
from intake.archive import IntakeArchive
from intake.receive import receive_station
from issue.freeze import freeze_station
from issue.register import IssueRegister
from measure.imports import RevisionInput, record_revision
from measure.revisions import RevisionStore
from report.journal import ReportJournal
from storage import open_database


def measurement(segment, draw, effect0, effect1, quota0=0, quota1=0):
    return {'source': {'record': 'test-record', 'segment': segment}, 'draw': draw,
            'choices': [{'treated': str(effect), 'control': '0', 'quota': quota}
                        for effect, quota in ((effect0, quota0), (effect1, quota1))]}


def tally(record):
    result = record.result
    return result.tail_count, result.eligible_count, result.probability


def enumerate_raw_assignments(design, raw_rows, quota_min, quota_max, threshold):
    roles = design['roles']
    public = design['public_draws']
    private = design.get('private_draws', {})
    raw_rules = design.get('local_rules', {})
    coordinates = [(None, name) for name in public]
    coordinates.extend((role, name) for role in roles for name in private.get(role, ()))
    tail = eligible = 0
    for bits in product((0, 1), repeat=len(coordinates)):
        allocation = dict(zip(coordinates, bits))
        quotas = []
        effects = []
        allowed = True
        for role in roles:
            values = {name: bit for (owner, name), bit in allocation.items() if owner in (None, role)}
            selected = [row['choices'][values[row['draw']]] for row in raw_rows[role]]
            quota = sum(row['quota'] for row in selected)
            quotas.append(quota)
            effects.append(sum((Fraction(row['treated']) - Fraction(row['control']) for row in selected), Fraction(0)))
            for rule in raw_rules.get(role, ()):
                if any(values[name] != bit for name, bit in rule['when'].items()):
                    continue
                upper = rule.get('quota_max')
                if rule.get('forbid') or quota < rule.get('quota_min', 0) or (upper is not None and quota > upper):
                    allowed = False
        if allowed and quota_min <= sum(quotas) <= quota_max:
            eligible += 1
            tail += sum(effects) >= Fraction(threshold)
    return tail, eligible, Fraction(tail, eligible) if eligible else None


def corrected_rows(sample):
    rows = deepcopy(sample['initial'])
    changes = {(row['source']['record'], row['source']['segment']): row for row in sample['correction']}
    rows['line-b'] = [changes.get((row['source']['record'], row['source']['segment']), row)
                      for row in rows['line-b']]
    return rows


class TrialTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='strip-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sites = ExitStack()
        self.center = ExitStack()
        self.addCleanup(self.sites.close)
        self.addCleanup(self.center.close)
        self.design = read_example('protocol.json')
        self.sample = read_example('measurements.json')
        self.reopen_sites()
        self.reopen_center()

    def reopen_sites(self):
        self.sites.close()
        self.revisions = {}
        self.issues = {}
        for index, role in enumerate(self.design['roles']):
            db = self.sites.enter_context(open_database(self.root / f'site-{index}.sqlite'))
            self.revisions[role] = RevisionStore(db)
            self.issues[role] = IssueRegister(db)

    def reopen_center(self):
        self.center.close()
        self.center_db = self.center.enter_context(open_database(self.root / 'center.sqlite'))
        self.archive = IntakeArchive(self.center_db)
        self.journal = ReportJournal(self.center_db)

    def register(self, design=None):
        design = self.design if design is None else design
        for role in design['roles']:
            register_protocol(self.revisions[role].registry, **design)

    def import_sample(self, design=None, initial=None):
        design = self.design if design is None else design
        initial = self.sample['initial'] if initial is None else initial
        self.register(design)
        return {role: record_revision(self.revisions[role], RevisionInput(design['trial_id'], role, initial[role]))
                for role in design['roles']}

    def correct(self, prior, rows=None):
        rows = self.sample['correction'] if rows is None else rows
        return record_revision(self.revisions[prior.role],
                               RevisionInput(prior.protocol.trial_id, prior.role, rows, prior.revision_id))

    def freeze(self, revision, issue_id):
        return freeze_station(self.revisions[revision.role], self.issues[revision.role],
                              revision.revision_id, issue_id)

    def receive(self, revision, issue_id):
        return receive_station(self.archive, self.freeze(revision, issue_id))

    def stage_pair(self, revisions, prefix='initial'):
        return tuple(self.receive(revisions[role], f'{prefix}-{role}').receipt_id for role in self.design['roles'])

    def report_counts(self):
        reports = self.center_db.execute('SELECT count(*) FROM reports').fetchone()[0]
        receipts = self.center_db.execute('SELECT count(*) FROM report_receipts').fetchone()[0]
        return reports, receipts

    def intake_counts(self):
        items = self.center_db.execute('SELECT count(*) FROM station_archive').fetchone()[0]
        receipts = self.center_db.execute('SELECT count(*) FROM station_receipts').fetchone()[0]
        return items, receipts
