import json
import sqlite3
from copy import deepcopy
from fractions import Fraction

from report.history import get_report
from report.publish import publish_report
from tests.support import TrialTest, corrected_rows, enumerate_raw_assignments, measurement, tally


class ReportTests(TrialTest):
    def publish(self, pair, quota_min=0, quota_max=1, threshold=2, **options):
        return publish_report(self.archive, self.journal, pair, quota_min, quota_max, threshold, **options)

    def original_and_corrected(self):
        revisions = self.import_sample()
        original = self.stage_pair(revisions)
        corrected = self.receive(self.correct(revisions['line-b']), 'corrected-line-b')
        return original, (original[0], corrected.receipt_id)

    def test_offline_tail(self):
        original, corrected = self.original_and_corrected()
        self.sites.close()
        for pair, rows in ((original, self.sample['initial']), (corrected, corrected_rows(self.sample))):
            for lower, upper, threshold in ((0, 1, 2), (0, 0, '3/2'), (1, 2, '1/3'), (2, 2, 2)):
                with self.subTest(pair=pair, quota=(lower, upper), threshold=threshold):
                    record, receipt = self.publish(pair, lower, upper, threshold)
                    oracle = enumerate_raw_assignments(self.design, rows, lower, upper, threshold)
                    self.assertEqual(tally(record), oracle, 'RANDOMIZATION_TAIL_MISMATCH')
                    self.assertEqual(receipt.report_id, record.report_id)

    def test_shared_assignment(self):
        original, corrected = self.original_and_corrected()
        self.sites.close()
        signed = [self.publish(pair) for pair in (original, corrected)]
        expected = [(0, 3, Fraction(0)), (1, 3, Fraction(1, 3))]
        results = [tally(record) for record, _ in signed]
        self.assertEqual(results, expected, 'RANDOMIZATION_TAIL_MISMATCH')
        downstream = []
        for (record, receipt), pair in zip(signed, (original, corrected)):
            history = get_report(self.archive, self.journal, record.report_id)
            self.assertEqual(history.record, record)
            self.assertEqual(history.receipt, receipt)
            parents = tuple(parent.receipt.receipt_id for parent in history.parents)
            self.assertEqual(parents, pair)
            downstream.append(parents)
        scenario = {
            'case_id': 'offline_tail.shared_assignment',
            'input': {'public_draw': 'U', 'private_draw': 'V', 'quota': [0, 1], 'threshold': '2',
                      'initial_effects': ['U', '1-U'], 'corrected_effects': ['U', 'U'],
                      'receipts': [original, corrected]},
            'expected': [[hits, total, str(probability)] for hits, total, probability in expected],
            'actual': [[hits, total, str(probability)] for hits, total, probability in results],
            'downstream_expected': [original, corrected],
            'downstream_actual': downstream,
            'code_paths': ['issue/evidence.py', 'intake/pairing.py', 'report/population.py',
                           'report/tail.py', 'report/history.py'],
            'oracle': 'Hand enumerate (U,V) = (0,0), (0,1), (1,0). Only the corrected last pair reaches 2.',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(scenario, sort_keys=True))

    def test_local_admission(self):
        design = deepcopy(self.design)
        design['local_rules'] = {'line-b': [{'when': {'U': 1, 'V': 0}, 'forbid': True}]}
        rows = corrected_rows(self.sample)
        pair = self.stage_pair(self.import_sample(design, rows))
        self.sites.close()
        record, _ = self.publish(pair)
        self.assertEqual(tally(record), (0, 2, Fraction(0)))
        self.assertEqual(tally(record), enumerate_raw_assignments(design, rows, 0, 1, 2))

    def test_multiplicity(self):
        rows = corrected_rows(self.sample)
        first = self.stage_pair(self.import_sample(self.design, rows), 'first')
        design = deepcopy(self.design)
        design['trial_id'] = 'strip-extra-draw'
        design['private_draws']['line-b'].append('W')
        expanded = deepcopy(rows)
        expanded['line-b'].append(measurement('neutral', 'W', 0, 0))
        extra = self.stage_pair(self.import_sample(design, expanded), 'extra')
        self.sites.close()
        original, _ = self.publish(first)
        duplicated, _ = self.publish(extra)
        self.assertEqual(tally(original), enumerate_raw_assignments(self.design, rows, 0, 1, 2))
        self.assertEqual(tally(duplicated), enumerate_raw_assignments(design, expanded, 0, 1, 2))
        self.assertEqual(tally(original), (1, 3, Fraction(1, 3)))
        self.assertEqual(tally(duplicated), (2, 6, Fraction(1, 3)))

    def test_same_private_name_at_both_stations(self):
        design = deepcopy(self.design)
        design['public_draws'] = []
        design['private_draws'] = {'line-a': ['X'], 'line-b': ['X']}
        rows = {role: [measurement(role, 'X', 0, 1, 0, 1)] for role in design['roles']}
        pair = self.stage_pair(self.import_sample(design, rows))
        self.sites.close()
        record, _ = self.publish(pair, 0, 2, 2)
        self.assertEqual(tally(record), (1, 4, Fraction(1, 4)))
        self.assertEqual(tally(record), enumerate_raw_assignments(design, rows, 0, 2, 2))

    def test_empty_condition(self):
        pair = self.stage_pair(self.import_sample())
        self.sites.close()
        record, receipt = self.publish(pair, 3, 3, 2)
        self.assertEqual(tally(record), (0, 0, None))
        self.assertEqual(record.result.status, 'no_eligible_allocations')
        self.assertEqual(self.journal.load_report(record.report_id), (record, receipt))

    def test_zero_tail_is_a_probability(self):
        pair = self.stage_pair(self.import_sample())
        self.sites.close()
        empty, _ = self.publish(pair, 3, 3, 2)
        zero, _ = self.publish(pair)
        self.assertEqual((empty.result.status, empty.result.probability), ('no_eligible_allocations', None))
        self.assertEqual((zero.result.status, zero.result.probability), ('calculated', Fraction(0)))
        self.assertEqual(zero.result.eligible_count, 3)
        self.assertEqual(self.journal.load_report(zero.report_id)[0], zero)

    def test_bad_pair(self):
        revisions = self.import_sample()
        pair = self.stage_pair(revisions)
        second_left = self.receive(revisions['line-a'], 'another-A').receipt_id
        self.sites.close()
        for invalid in ((pair[0], second_left), pair[::-1]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.publish(invalid)
        with self.assertRaises(KeyError):
            self.publish((pair[0], 999))
        self.assertEqual(self.report_counts(), (0, 0))

    def test_cross_trial(self):
        first = self.stage_pair(self.import_sample(), 'first')
        design = self.design | {'trial_id': 'second-trial'}
        second = self.stage_pair(self.import_sample(design), 'second')
        self.sites.close()
        record, _ = self.publish(first)
        self.assertEqual(tally(record), (0, 3, Fraction(0)))
        with self.assertRaisesRegex(ValueError, 'different trials'):
            self.publish((first[0], second[1]))
        self.assertEqual(self.report_counts(), (1, 1))

    def test_invalid_request(self):
        pair = self.stage_pair(self.import_sample())
        self.sites.close()
        for lower, upper, threshold in ((2, 1, 2), (0, 1, '1/0'), (0, True, 2), (0, 1, 0.5)):
            with self.subTest(request=(lower, upper, threshold)), self.assertRaises(ValueError):
                self.publish(pair, lower, upper, threshold)
        self.assertEqual(self.report_counts(), (0, 0))

    def test_rollback(self):
        original, corrected = self.original_and_corrected()
        self.sites.close()
        old, old_receipt = self.publish(original)
        observed = []

        def refuse_write():
            observed.append(self.report_counts())
            raise sqlite3.OperationalError('report write refused before commit')

        with self.assertRaisesRegex(sqlite3.OperationalError, 'before commit'):
            self.publish(corrected, before_commit=refuse_write)
        self.assertEqual(observed, [(2, 2)])
        self.reopen_center()
        self.assertEqual(self.report_counts(), (1, 1))
        self.assertEqual(self.journal.load_report(old.report_id), (old, old_receipt))
        record, receipt = self.publish(corrected)
        self.assertEqual(self.report_counts(), (2, 2))
        self.assertEqual(tally(record), (1, 3, Fraction(1, 3)))
        self.assertEqual(get_report(self.archive, self.journal, record.report_id).receipt, receipt)
