from copy import deepcopy
from fractions import Fraction

from design.registry import register_protocol
from measure.imports import RevisionInput, record_revision
from measure.local_review import review_station
from tests.support import TrialTest, measurement


class MeasurementTests(TrialTest):
    def test_local_review(self):
        revisions = self.import_sample()
        right = revisions['line-b']
        store = self.revisions[right.role]
        assignment = {'U': 1, 'V': 1}
        original = review_station(store, right.revision_id, assignment)
        updated = self.correct(right)
        corrected = review_station(store, updated.revision_id, assignment)
        self.assertTrue(original.allowed)
        self.assertEqual((original.totals.quota, original.totals.effect), (1, Fraction(0)))
        self.assertEqual((corrected.totals.quota, corrected.totals.effect), (1, Fraction(1)))
        self.assertEqual(corrected.totals.contributions[0].source.segment, 'strip-B1')
        self.assertEqual(updated.parent_id, right.revision_id)
        self.assertEqual(review_station(store, right.revision_id, assignment), original)

    def test_protocol_immutable(self):
        design = deepcopy(self.design)
        design['local_rules'] = {'line-b': [{'when': {'U': 1}, 'quota_min': 1}]}
        right = self.import_sample(design)['line-b']
        store = self.revisions[right.role]
        self.assertEqual(register_protocol(store.registry, **design), right.protocol)
        changed = deepcopy(design)
        changed['roles'].reverse()
        changed['local_rules'] = {}
        with self.assertRaises(ValueError):
            register_protocol(store.registry, **changed)
        stored = store.get_revision(right.revision_id)
        self.assertEqual(stored.protocol.roles, ('line-a', 'line-b'))
        self.assertEqual(stored.protocol, right.protocol)
        disallowed = review_station(store, right.revision_id, {'U': 1, 'V': 0})
        allowed = review_station(store, right.revision_id, {'U': 1, 'V': 1})
        self.assertEqual((disallowed.allowed, disallowed.totals.quota, disallowed.totals.effect),
                         (False, 0, Fraction(0)))
        self.assertTrue(allowed.allowed)

    def test_explicit_parent(self):
        self.register()
        store = self.revisions['line-a']
        first = record_revision(store, RevisionInput('strip-01', 'line-a', [
            measurement('S2', 'U', 0, '2/3'), measurement('S1', 'U', 0, '1/3')]))
        second = self.correct(first, [measurement('S2', 'U', 0, '5/3')])
        third = self.correct(first, [measurement('S1', 'U', 0, '4/3')])
        audits = [review_station(store, revision.revision_id, {'U': 1}) for revision in (first, second, third)]
        self.assertEqual([audit.totals.effect for audit in audits], [Fraction(1), Fraction(2), Fraction(2)])
        self.assertEqual([item.effect for item in audits[2].totals.contributions],
                         [Fraction(4, 3), Fraction(2, 3)])
        self.assertEqual(store.get_revision(third.revision_id).parent_id, first.revision_id)
        self.assertEqual(store.get_revision(second.revision_id), second)

    def test_signed_effect(self):
        self.register()
        store = self.revisions['line-a']
        row = measurement('S1', 'U', '-1/3', '1/3', 1, 1)
        revision = record_revision(store, RevisionInput('strip-01', 'line-a', [row]))
        audits = [review_station(store, revision.revision_id, {'U': bit}) for bit in (0, 1)]
        self.assertEqual([(audit.allowed, audit.totals.quota, audit.totals.effect) for audit in audits],
                         [(True, 1, Fraction(-1, 3)), (True, 1, Fraction(1, 3))])
        self.assertEqual(audits[0].totals.contributions[0].source.record, 'test-record')
        for bad in ({}, {'U': True}, {'U': 2}, {'U': 0, 'V': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                review_station(store, revision.revision_id, bad)
        with self.assertRaises(KeyError):
            review_station(store, 999, {'U': 0})

    def test_bad_revision(self):
        self.register()
        store = self.revisions['line-a']
        good = measurement('S1', 'U', 0, 1)
        missing = measurement('S2', 'U', 0, 1)
        del missing['source']
        invalid = []
        for field, value in (('quota', True), ('quota', -1), ('treated', '1/0'), ('control', 1.5)):
            row = measurement('S2', 'U', 0, 1)
            row['choices'][1][field] = value
            invalid.append(row)
        invalid.extend((missing, measurement('S2', 'bad-draw', 0, 1), deepcopy(good)))
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValueError):
                record_revision(store, RevisionInput('strip-01', 'line-a', [good, row]))
        self.assertEqual(store.db.execute('SELECT count(*) FROM measurement_revisions').fetchone()[0], 0)
        first = record_revision(store, RevisionInput('strip-01', 'line-a', [good]))
        with self.assertRaises(KeyError):
            record_revision(store, RevisionInput('strip-01', 'line-a', [good], 999))
        with self.assertRaises(ValueError):
            self.correct(first, [measurement('unknown-source', 'U', 0, 1)])
        self.assertEqual(store.db.execute('SELECT count(*) FROM measurement_revisions').fetchone()[0], 1)

    def test_protocol_rejects_invalid_definitions(self):
        registry = self.revisions['line-a'].registry
        for changes in (
            {'roles': ['line-a', 'line-a']},
            {'public_draws': ['U', 'U']},
            {'public_draws': ['U', 'V', 'W', 'X']},
            {'private_draws': {'line-a': ['U']}},
            {'private_draws': {'line-a': ['V', 'W', 'X', 'Y', 'Z', 'K']}},
            {'local_rules': {'line-a': [{'when': {'V': 1}}]}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                register_protocol(registry, **(self.design | changes))
        with self.assertRaises(KeyError):
            registry.get_protocol('strip-01')
