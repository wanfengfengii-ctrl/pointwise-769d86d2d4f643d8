import sqlite3
import unittest
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.quota_reissue import MAIN_PROTOCOL, MAIN_ROWS, ROLES, SHARED_PROTOCOL, SHARED_ROWS
from design.registry import register_protocol
from intake.archive import IntakeArchive
from intake.receive import receive_station
from issue.envelope import decode_envelope, encode_envelope
from issue.freeze import freeze_executable_station, freeze_station, redeem_station_ticket
from issue.register import IssueRegister
from measure.imports import RevisionInput, record_revision
from measure.revisions import RevisionStore
from report.coupling import reissue_choice
from report.executable_population import enumerate_complete_allocations
from report.ticket_history import get_ticket
from report.ticket_journal import TicketJournal
from report.ticket_publish import draw_ticket, reissue_ticket
from storage import open_database


class ScriptedRandbelow:
    def __init__(self, answers):
        self.answers = list(answers)
        self.bounds = []

    def __call__(self, upper):
        if type(upper) is not int or upper <= 0:
            raise AssertionError(f'invalid random bound {upper!r}')
        self.bounds.append(upper)
        if not self.answers:
            raise AssertionError(f'no scripted answer for randbelow({upper})')
        answer = self.answers.pop(0)
        if type(answer) is not int or not 0 <= answer < upper:
            raise AssertionError(f'scripted answer {answer!r} outside [0, {upper})')
        return answer


class NoCallback:
    def __call__(self, upper):
        raise AssertionError('randbelow must not be called')


class ExecutableFlowTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='quota-ticket-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.center_db = self.stack.enter_context(open_database(self.root / 'center.sqlite'))
        self.archive = IntakeArchive(self.center_db)
        self.journal = TicketJournal(self.center_db)
        self.stores = {}
        self.receipt_ids = self._stage(MAIN_PROTOCOL, MAIN_ROWS, 'main')

    def _stage(self, protocol, rows, prefix):
        receipt_ids = []
        for role in ROLES:
            db = self.stack.enter_context(open_database(self.root / f'{prefix}-{role}.sqlite'))
            revisions = RevisionStore(db)
            issues = IssueRegister(db)
            register_protocol(revisions.registry, **protocol)
            revision = record_revision(
                revisions, RevisionInput(protocol['trial_id'], role, rows[role]))
            wire = freeze_executable_station(revisions, issues, revision.revision_id,
                                             f'{prefix}-{role}')
            receipt = receive_station(self.archive, wire)
            self.stores[role] = (revisions, issues)
            receipt_ids.append(receipt.receipt_id)
        return tuple(receipt_ids)

    def _pair(self):
        from intake.executable_pairing import resolve_executable_pair
        return resolve_executable_pair(self.archive, self.receipt_ids)

    def test_freeze_is_deterministic_and_distinct(self):
        revisions, issues = self.stores[ROLES[0]]
        revision = revisions.get_revision(1)
        first = freeze_executable_station(revisions, issues, revision.revision_id, 'main-line-a')
        second = freeze_executable_station(revisions, issues, revision.revision_id, 'main-line-a')
        self.assertEqual(first, second)
        envelope = decode_envelope(first)
        self.assertEqual(envelope.version, 2)
        body = envelope.body.decode('ascii')
        # Private draw names and values never appear in the station piece.
        self.assertNotIn('A-low', body)
        self.assertNotIn('A-high', body)
        pair = self._pair()
        identifiers = {item.allocation_id for item in pair.first.allocations}
        self.assertEqual(len(identifiers), len(pair.first.allocations))

    def test_v1_issue_id_cannot_be_reissued_as_v2(self):
        revisions, issues = self.stores[ROLES[0]]
        revision = revisions.get_revision(1)
        freeze_station(revisions, issues, revision.revision_id, 'v1-issue')
        with self.assertRaisesRegex(ValueError, 'version 1'):
            freeze_executable_station(revisions, issues, revision.revision_id, 'v1-issue')

    def test_initial_draw_uniform_and_redeemable(self):
        pair = self._pair()
        population = enumerate_complete_allocations(pair, 0, 1)
        self.assertEqual(len(population), 4)
        seen = set()
        for index in range(4):
            ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                                 0, 1, ScriptedRandbelow((index,)))
            self.assertIsNone(ticket['initial_ticket_id'])
            self.assertIsNone(ticket['kept'])
            self.assertEqual(ticket['quota_min'], 0)
            self.assertEqual(ticket['quota_max'], 1)
            seen.add(tuple(seg['allocation_id'] for seg in ticket['segments']))
        self.assertEqual(len(seen), 4)

    def test_empty_population_draws_no_callback(self):
        ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                             4, 4, NoCallback())
        self.assertIsNone(ticket['segments'])
        self.assertIsNone(ticket['kept'])

    def test_reissue_retention_and_replay(self):
        initial = draw_ticket(self.archive, self.journal, self.receipt_ids,
                              0, 1, ScriptedRandbelow((0,)))
        # Script the reissue onto every branch by exhausting the small bounds.
        reissued = reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                                  1, 3, ScriptedRandbelow((0,)))
        self.assertEqual(reissued['initial_ticket_id'], initial['ticket_id'])
        self.assertIn(reissued['kept'], (True, False))
        # Same ticket, same window: stored value without invoking the callback.
        again = reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                               1, 3, NoCallback())
        self.assertEqual(again, reissued)

    def test_reissue_window_conflict_rejected(self):
        initial = draw_ticket(self.archive, self.journal, self.receipt_ids,
                              0, 1, ScriptedRandbelow((0,)))
        reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                       1, 3, ScriptedRandbelow((0,)))
        with self.assertRaisesRegex(ValueError, 'another quota window'):
            reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                           2, 3, NoCallback())

    def test_empty_new_population_reissue(self):
        initial = draw_ticket(self.archive, self.journal, self.receipt_ids,
                              0, 1, ScriptedRandbelow((0,)))
        reissued = reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                                  4, 4, NoCallback())
        self.assertIsNone(reissued['segments'])
        self.assertFalse(reissued['kept'])
        # It still counts as the single committed reissue and replays.
        self.assertEqual(reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                                        4, 4, NoCallback()), reissued)

    def test_station_redeems_own_segment_only(self):
        ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                             0, 1, ScriptedRandbelow((0,)))
        for index, role in enumerate(ROLES):
            revisions, issues = self.stores[role]
            review = redeem_station_ticket(
                revisions, issues, f'main-{role}', ticket['segments'][index])
            self.assertTrue(review.allowed)
            self.assertEqual(review.totals.quota,
                             ticket['segments'][index] and review.totals.quota)
        # A segment naming another station's issue is unknown here.
        revisions_a, issues_a = self.stores[ROLES[0]]
        with self.assertRaises(KeyError):
            redeem_station_ticket(revisions_a, issues_a, 'main-line-a',
                                  ticket['segments'][1])
        # Passing a segment whose issue does not match the requested issue id
        # is a role/identity conflict.
        foreign = dict(ticket['segments'][0])
        with self.assertRaises(ValueError):
            redeem_station_ticket(revisions_a, issues_a, 'main-line-b',
                                  foreign)

    def test_unknown_ticket_and_bad_roles(self):
        with self.assertRaises(KeyError):
            reissue_ticket(self.archive, self.journal, 999, 1, 3, NoCallback())
        self.assertIsNone(get_ticket(self.archive, self.journal, 999))


class PersistenceAndRejectionTest(ExecutableFlowTest):
    def test_before_commit_rollback_then_retry(self):
        def refuse():
            raise sqlite3.OperationalError('ticket write refused before commit')

        before = self.center_db.execute('SELECT count(*) FROM tickets').fetchone()[0]
        with self.assertRaisesRegex(sqlite3.OperationalError, 'refused'):
            draw_ticket(self.archive, self.journal, self.receipt_ids,
                        0, 1, ScriptedRandbelow((0,)), before_commit=refuse)
        # Failed write leaves no new ticket and can be retried cleanly.
        self.assertEqual(self.center_db.execute('SELECT count(*) FROM tickets').fetchone()[0], before)
        ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                             0, 1, ScriptedRandbelow((0,)))
        self.assertEqual(get_ticket(self.archive, self.journal, ticket['ticket_id']), ticket)

    def test_reopen_center_retrieves_ticket(self):
        ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                             0, 1, ScriptedRandbelow((0,)))
        reissued = reissue_ticket(self.archive, self.journal, ticket['ticket_id'],
                                  1, 3, ScriptedRandbelow((0,)))
        self.stack.close()
        with open_database(self.root / 'center.sqlite') as reopened:
            archive = IntakeArchive(reopened)
            journal = TicketJournal(reopened)
            self.assertEqual(get_ticket(archive, journal, ticket['ticket_id']), ticket)
            self.assertEqual(get_ticket(archive, journal, reissued['ticket_id']), reissued)
            # Replaying the committed reissue after reopen still uses no callback.
            self.assertEqual(reissue_ticket(archive, journal, ticket['ticket_id'],
                                            1, 3, NoCallback()), reissued)

    def test_duplicate_intake_returns_same_receipt(self):
        pair = self._pair()
        wire = self.archive.get_station(pair.first.receipt_id).wire
        again = receive_station(self.archive, wire)
        self.assertEqual(again.receipt_id, pair.first.receipt_id)

    def test_tampered_v2_piece_rejected(self):
        pair = self._pair()
        wire = self.archive.get_station(pair.first.receipt_id).wire
        tampered = wire.replace(b'"allocations"', b'"allocations2"', 1)
        self.assertNotEqual(tampered, wire)
        with self.assertRaises(ValueError):
            receive_station(IntakeArchive(self._fresh_center()), tampered)

    def _fresh_center(self):
        path = self.root / 'isolated-center.sqlite'
        return self.stack.enter_context(open_database(path))

    def test_duplicate_allocation_identity_rejected(self):
        pair = self._pair()
        wire = self.archive.get_station(pair.first.receipt_id).wire
        envelope = decode_envelope(wire)
        import json
        body = json.loads(envelope.body)
        # Replace a distinct entry with a copy of the first one, keeping the
        # table size valid, so the duplicate-identity check is what fires.
        body['allocations'][1] = dict(body['allocations'][0])
        duplicate = encode_envelope(type(envelope)(**{**envelope.__dict__,
                                                      'body': json.dumps(body, sort_keys=True,
                                                                         separators=(',', ':')).encode('ascii')}))
        with self.assertRaisesRegex(ValueError, 'duplicate executable allocation identity'):
            receive_station(IntakeArchive(self._fresh_center()), duplicate)

    def test_bad_randbelow_rejected(self):
        def bad(_):
            return 99

        with self.assertRaises(ValueError):
            draw_ticket(self.archive, self.journal, self.receipt_ids, 0, 1, bad)
        with self.assertRaises(ValueError):
            draw_ticket(self.archive, self.journal, self.receipt_ids, 0, 1, lambda _: 'x')

    def test_v1_piece_cannot_feed_ticket_draw(self):
        # Build a self-contained pair inside one isolated center archive.
        isolated = IntakeArchive(self._fresh_center())
        isolated_ids = []
        for role in ROLES:
            db = self.stack.enter_context(open_database(self.root / f'v1pair-{role}.sqlite'))
            revisions = RevisionStore(db)
            issues = IssueRegister(db)
            register_protocol(revisions.registry, **MAIN_PROTOCOL)
            revision = record_revision(
                revisions, RevisionInput(MAIN_PROTOCOL['trial_id'], role, MAIN_ROWS[role]))
            wire = freeze_station(revisions, issues, revision.revision_id, f'v1pair-{role}')
            isolated_ids.append(receive_station(isolated, wire).receipt_id)
        from intake.executable_pairing import resolve_executable_pair
        with self.assertRaisesRegex(ValueError, 'version 2'):
            resolve_executable_pair(isolated, tuple(isolated_ids))

    def test_reissue_before_commit_rollback_then_retry(self):
        initial = draw_ticket(self.archive, self.journal, self.receipt_ids,
                              0, 1, ScriptedRandbelow((0,)))
        before = self.center_db.execute('SELECT count(*) FROM ticket_reissues').fetchone()[0]

        def refuse():
            raise sqlite3.OperationalError('reissue write refused before commit')

        with self.assertRaisesRegex(sqlite3.OperationalError, 'refused'):
            reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                           1, 3, ScriptedRandbelow((0,)), before_commit=refuse)
        self.assertEqual(self.center_db.execute('SELECT count(*) FROM ticket_reissues').fetchone()[0], before)
        reissued = reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                                  1, 3, ScriptedRandbelow((0,)))
        self.assertEqual(reissue_ticket(self.archive, self.journal, initial['ticket_id'],
                                        1, 3, NoCallback()), reissued)

    def test_redeem_unknown_allocation_rejected(self):
        ticket = draw_ticket(self.archive, self.journal, self.receipt_ids,
                             0, 1, ScriptedRandbelow((0,)))
        revisions, issues = self.stores[ROLES[0]]
        bad_segment = dict(ticket['segments'][0])
        bad_segment['allocation_id'] = 'deadbeef' * 4
        with self.assertRaisesRegex(ValueError, 'not part of this station issue'):
            redeem_station_ticket(revisions, issues, 'main-line-a', bad_segment)

    def test_kept_means_both_stations_redeem_original_allocation(self):
        pair = self._pair()
        old_population = enumerate_complete_allocations(pair, 0, 1)
        new_population = enumerate_complete_allocations(pair, 1, 3)
        # Exhaust every random path for each initial allocation.
        for initial_index, initial in enumerate(old_population):
            initial_ticket = draw_ticket(
                self.archive, self.journal, self.receipt_ids, 0, 1,
                ScriptedRandbelow((initial_index,)))
            distribution = Counter()

            def collect(answers):
                bounds = []

                def randbelow(size):
                    bounds.append(size)
                    if len(bounds) > len(answers):
                        raise _Fork(size)
                    return answers[len(bounds) - 1]

                from report.coupling import reissue_choice
                try:
                    choice, kept = reissue_choice(randbelow, old_population, new_population, initial)
                except _Fork:
                    for answer in range(bounds[-1]):
                        collect(answers + [answer])
                    return
                distribution[(choice.key(), kept)] += 1

            collect([])
            for (key, kept), _count in distribution.items():
                if kept:
                    self.assertEqual(key, initial.key())
                    # Both segment allocation ids must equal the initial ticket's.
                    self.assertEqual(key, tuple(seg['allocation_id']
                                                for seg in initial_ticket['segments']))
                else:
                    self.assertNotEqual(key, initial.key())


class SharedDrawTest(unittest.TestCase):
    def test_forbidden_allocation_never_issued(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with open_database(root / 'center.sqlite') as center:
                archive = IntakeArchive(center)
                receipt_ids = []
                with ExitStack() as stack:
                    for role in ROLES:
                        db = stack.enter_context(open_database(root / f'shared-{role}.sqlite'))
                        revisions = RevisionStore(db)
                        issues = IssueRegister(db)
                        register_protocol(revisions.registry, **SHARED_PROTOCOL)
                        revision = record_revision(
                            revisions, RevisionInput(SHARED_PROTOCOL['trial_id'], role,
                                                     SHARED_ROWS[role]))
                        wire = freeze_executable_station(revisions, issues, revision.revision_id,
                                                         f'shared-{role}')
                        receipt_ids.append(receive_station(archive, wire).receipt_id)
                from intake.executable_pairing import resolve_executable_pair
                pair = resolve_executable_pair(archive, tuple(receipt_ids))
                self.assertEqual(len(enumerate_complete_allocations(pair, 0, 1)), 3)
                self.assertEqual(len(enumerate_complete_allocations(pair, 1, 1)), 2)
                self.assertEqual(len(enumerate_complete_allocations(pair, 2, 2)), 0)
                # Every issued allocation has equal public U across both stations.
                for complete in enumerate_complete_allocations(pair, 0, 1):
                    self.assertEqual(complete.left.public_values,
                                     complete.right.public_values)

    def test_fully_forbidden_station_yields_empty_piece_and_ticket(self):
        protocol = deepcopy(SHARED_PROTOCOL)
        protocol['local_rules'] = {'line-b': [{'when': {}, 'forbid': True}]}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with open_database(root / 'center.sqlite') as center:
                archive = IntakeArchive(center)
                journal = TicketJournal(center)
                receipt_ids = []
                with ExitStack() as stack:
                    for role in ROLES:
                        db = stack.enter_context(open_database(root / f'forbid-{role}.sqlite'))
                        revisions = RevisionStore(db)
                        issues = IssueRegister(db)
                        register_protocol(revisions.registry, **protocol)
                        revision = record_revision(
                            revisions, RevisionInput(protocol['trial_id'], role,
                                                     SHARED_ROWS[role]))
                        wire = freeze_executable_station(revisions, issues, revision.revision_id,
                                                         f'forbid-{role}')
                        receipt_ids.append(receive_station(archive, wire).receipt_id)
                ticket = draw_ticket(archive, journal, tuple(receipt_ids), 0, 1, NoCallback())
                self.assertIsNone(ticket['segments'])


class CouplingDistributionTest(unittest.TestCase):
    class Alloc:
        def __init__(self, key):
            self.key_value = key
            self.left = type('Side', (), {'allocation_id': key[0]})()
            self.right = type('Side', (), {'allocation_id': key[1]})()

        def key(self):
            return self.key_value

    def _populations(self, m, n, k):
        old = tuple(self.Alloc((f'o{i}', f'o{i}')) for i in range(m))
        shared = old[:k]
        new = shared + tuple(self.Alloc((f'n{i}', f'n{i}')) for i in range(n - k))
        return old, new

    def _exact(self, old, new, initial):
        distribution = Counter()

        def descend(answers):
            bounds = []

            def randbelow(size):
                bounds.append(size)
                if len(bounds) > len(answers):
                    raise _Fork(size)
                return answers[len(bounds) - 1]

            try:
                choice, kept = reissue_choice(randbelow, old, new, initial)
            except _Fork:
                bound = bounds[-1]
                for answer in range(bound):
                    descend(answers + [answer])
                return
            weight = Fraction(1, 1)
            for bound in bounds:
                weight /= bound
            distribution[(choice.key(), kept)] += weight

        descend([])
        return distribution

    def test_exact_uniform_and_maximal_retention(self):
        for m in range(1, 6):
            for n in range(1, 6):
                for k in range(min(m, n) + 1):
                    old, new = self._populations(m, n, k)
                    joint = Counter()
                    retention = Fraction(0)
                    for initial in old:
                        distribution = self._exact(old, new, initial)
                        self.assertEqual(sum(distribution.values(), Fraction(0)), 1)
                        for (key, kept), weight in distribution.items():
                            joint[key] += weight / m
                            if kept:
                                retention += weight / m
                    self.assertEqual(set(joint), {a.key() for a in new})
                    for weight in joint.values():
                        self.assertEqual(weight, Fraction(1, n))
                    self.assertEqual(retention, Fraction(k, max(m, n)))

    def test_window_relationship_guarantees(self):
        # Identical nonempty windows retain everything; disjoint windows replace.
        old, new = self._populations(4, 4, 4)
        retention = Fraction(0)
        for initial in old:
            for (_, kept), weight in self._exact(old, new, initial).items():
                retention += weight / 4 if kept else 0
        self.assertEqual(retention, 1)
        disjoint_old, disjoint_new = self._populations(3, 5, 0)
        retention = Fraction(0)
        joint = Counter()
        for initial in disjoint_old:
            for (key, kept), weight in self._exact(disjoint_old, disjoint_new, initial).items():
                self.assertFalse(kept)
                joint[key] += weight / 3
        self.assertEqual(retention, 0)
        self.assertTrue(all(weight == Fraction(1, 5) for weight in joint.values()))


class MainExampleDistributionTest(ExecutableFlowTest):
    """Pins the exact QUOTA_REISSUE.md main-example numbers."""

    def test_main_example_exact_retention_and_uniformity(self):
        pair = self._pair()
        old_population = enumerate_complete_allocations(pair, 0, 1)
        new_population = enumerate_complete_allocations(pair, 1, 3)
        self.assertEqual((len(old_population), len(new_population)), (4, 6))
        intersection = {a.key() for a in old_population} & {a.key() for a in new_population}
        self.assertEqual(len(intersection), 2)
        harness = CouplingDistributionTest()
        joint = Counter()
        retention = Fraction(0)
        for initial in old_population:
            distribution = harness._exact(old_population, new_population, initial)
            for (key, kept), weight in distribution.items():
                joint[key] += weight / 4
                if kept:
                    retention += weight / 4
        self.assertEqual(len(joint), 6)
        self.assertTrue(all(weight == Fraction(1, 6) for weight in joint.values()))
        self.assertEqual(retention, Fraction(1, 3))


class _Fork(Exception):
    def __init__(self, bound):
        self.bound = bound


if __name__ == '__main__':
    unittest.main()
