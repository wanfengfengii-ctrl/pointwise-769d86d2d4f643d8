from fractions import Fraction

from design.registry import register_protocol
from intake.receive import receive_station
from measure.local_review import review_station
from report.history import get_report
from report.publish import publish_report
from tests.support import TrialTest, tally


class HistoryTests(TrialTest):
    def test_history(self):
        revisions = self.import_sample()
        original_pair = self.stage_pair(revisions)
        self.sites.close()
        original, original_receipt = publish_report(self.archive, self.journal, original_pair, 0, 1, 2)
        original_history = get_report(self.archive, self.journal, original.report_id)
        self.reopen_sites()
        corrected = self.correct(revisions['line-b'])
        new_receipt = self.receive(corrected, 'corrected-line-b')
        new_pair = (original_pair[0], new_receipt.receipt_id)
        self.sites.close()
        new, new_report_receipt = publish_report(self.archive, self.journal, new_pair, 0, 1, '2')
        self.reopen_center()
        history_new = get_report(self.archive, self.journal, new.report_id)
        history_original = get_report(self.archive, self.journal, original.report_id)
        self.assertEqual(history_original, original_history)
        self.assertEqual(history_original.receipt, original_receipt)
        self.assertEqual(history_new.receipt, new_report_receipt)
        self.assertEqual(history_new.record, new)
        self.assertEqual(tally(history_original.record), (0, 3, Fraction(0)))
        self.assertEqual(tally(history_new.record), (1, 3, Fraction(1, 3)))
        self.assertEqual(tuple(parent.receipt.receipt_id for parent in history_original.parents), original_pair)
        self.assertEqual(tuple(parent.receipt.receipt_id for parent in history_new.parents), new_pair)
        self.assertEqual(self.report_counts(), (2, 2))

    def test_unknown_report(self):
        self.assertIsNone(get_report(self.archive, self.journal, 999))
        self.assertEqual(self.report_counts(), (0, 0))

    def test_reinitialize(self):
        custom = self.design | {'trial_id': 'operator-trial'}
        revisions = self.import_sample(custom)
        original = revisions['line-b']
        corrected = self.correct(original)
        left_receipt = self.receive(revisions['line-a'], 'operator-A')
        wire = self.freeze(corrected, 'operator-B')
        right_receipt = receive_station(self.archive, wire)
        pair = (left_receipt.receipt_id, right_receipt.receipt_id)
        self.sites.close()
        record, report_receipt = publish_report(self.archive, self.journal, pair, 0, 1, 2)
        before = get_report(self.archive, self.journal, record.report_id)
        self.reopen_sites()
        self.reopen_center()
        right_store = self.revisions['line-b']
        same_protocol = register_protocol(right_store.registry, **custom)
        self.assertEqual(same_protocol, corrected.protocol)
        self.assertEqual(right_store.get_revision(original.revision_id), original)
        self.assertEqual(right_store.get_revision(corrected.revision_id), corrected)
        updated = review_station(right_store, corrected.revision_id, {'U': 1, 'V': 0})
        self.assertEqual(updated.totals.effect, Fraction(1))
        self.assertEqual(self.freeze(corrected, 'operator-B'), wire)
        self.sites.close()
        self.assertEqual(receive_station(self.archive, wire), right_receipt)
        self.assertEqual(self.archive.get_receipt(left_receipt.receipt_id), left_receipt)
        self.assertEqual(self.archive.get_station(right_receipt.receipt_id).wire, wire)
        after = get_report(self.archive, self.journal, record.report_id)
        self.assertEqual(after, before)
        self.assertEqual(after.receipt, report_receipt)
        self.assertEqual(self.intake_counts(), (2, 2))
        self.assertEqual(self.report_counts(), (1, 1))
