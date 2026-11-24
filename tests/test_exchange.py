import json
from collections import Counter
from dataclasses import replace
from fractions import Fraction

from intake.receive import receive_station
from issue.envelope import decode_envelope, encode_envelope
from tests.support import TrialTest
from values import canonical_json


class ExchangeTests(TrialTest):
    def test_repeat_receipt(self):
        left = self.import_sample()['line-a']
        wire = self.freeze(left, 'A-1')
        first = receive_station(self.archive, wire)
        self.assertEqual(receive_station(self.archive, wire), first)
        self.assertEqual(self.freeze(left, 'A-1'), wire)
        self.assertEqual(self.archive.get_station(first.receipt_id).wire, wire)
        self.assertEqual(self.intake_counts(), (1, 1))

    def test_receipt_after_reopen(self):
        right = self.import_sample()['line-b']
        wire = self.freeze(right, 'B-1')
        first = receive_station(self.archive, wire)
        self.reopen_center()
        again = receive_station(self.archive, wire)
        self.assertEqual(first, again)
        self.assertEqual(self.archive.get_receipt(again.receipt_id), first)
        self.assertEqual(self.intake_counts(), (1, 1))

    def test_shared_evidence(self):
        right = self.import_sample()['line-b']
        correction = self.correct(right)
        first = self.receive(right, 'B-1')
        second = self.receive(correction, 'B-2')
        archived = [self.archive.get_station(receipt.receipt_id) for receipt in (first, second)]
        projections = []
        for item in archived:
            margin = Counter()
            buckets = {}
            for entry in item.station.counts:
                margin[entry.quota, entry.effect] += entry.count
                buckets[entry.public_values, entry.quota] = (entry.effect, entry.count)
            projections.append((margin, buckets))
            self.assertEqual(item.station.public_draws, ('U',))
            self.assertEqual(item.station.private_draw_count, 1)
            self.assertNotIn(b'B-source', item.wire)
            self.assertNotIn(b'strip-B1', item.wire)
            self.assertNotIn(b'"V"', item.wire)
        self.assertEqual(projections[0][0], projections[1][0])
        for index, (item, (_, buckets)) in enumerate(zip(archived, projections)):
            expected = {((u,), v): (Fraction(1 - u if index == 0 else u), 1)
                        for u in (0, 1) for v in (0, 1)}
            self.assertEqual(buckets, expected)
            self.assertEqual(receive_station(self.archive, item.wire), item.receipt)

    def test_conflicting_piece(self):
        revisions = self.import_sample()
        original = self.freeze(revisions['line-a'], 'same-issue')
        conflicting = self.freeze(revisions['line-b'], 'same-issue')
        first = receive_station(self.archive, original)
        self.assertNotEqual(conflicting, original)
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            receive_station(self.archive, conflicting)
        self.assertEqual(receive_station(self.archive, original), first)
        self.assertEqual(self.archive.get_station(first.receipt_id).wire, original)
        self.assertEqual(self.intake_counts(), (1, 1))

    def test_issue_binding(self):
        right = self.import_sample()['line-b']
        wire = self.freeze(right, 'B-1')
        receipt = receive_station(self.archive, wire)
        correction = self.correct(right)
        with self.assertRaisesRegex(ValueError, 'another revision'):
            self.freeze(correction, 'B-1')
        self.assertEqual(self.freeze(right, 'B-1'), wire)
        self.assertEqual(self.archive.get_station(receipt.receipt_id).wire, wire)
        self.assertEqual(receive_station(self.archive, wire), receipt)

    def test_malformed_evidence(self):
        left = self.import_sample()['line-a']
        wire = self.freeze(left, 'A-1')
        tampered = wire.replace(b'"A-1"', b'"A-2"', 1)
        self.assertNotEqual(tampered, wire)
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            receive_station(self.archive, tampered)
        envelope = decode_envelope(wire)
        body = json.loads(envelope.body)
        body['counts'][0]['count'] = 2
        invalid_counts = replace(envelope, body=canonical_json(body).encode('ascii'))
        with self.assertRaisesRegex(ValueError, 'exceeds assignments'):
            receive_station(self.archive, encode_envelope(invalid_counts))
        self.assertEqual(self.intake_counts(), (0, 0))
