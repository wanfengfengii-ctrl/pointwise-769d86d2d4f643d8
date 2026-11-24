import json
from contextlib import ExitStack

from design.registry import register_protocol
from intake.archive import IntakeArchive
from intake.receive import receive_station
from issue.freeze import freeze_station
from issue.register import IssueRegister
from measure.imports import RevisionInput, record_revision
from measure.revisions import RevisionStore
from report.journal import ReportJournal
from report.publish import publish_report
from storage import open_database


ROLES = ("line-a", "line-b")
MAIN_PROTOCOL = {
    "trial_id": "strip-quota-reissue",
    "roles": ROLES,
    "public_draws": [],
    "private_draws": {"line-a": ["A-low", "A-high"], "line-b": ["B-choice"]},
}
SHARED_PROTOCOL = {
    "trial_id": "strip-quota-shared",
    "roles": ROLES,
    "public_draws": ["U"],
    "private_draws": {"line-b": ["B-gate"]},
    "local_rules": {"line-b": [{"when": {"U": 1, "B-gate": 1}, "forbid": True}]},
}


def row(role, segment, draw, low, high):
    return {
        "source": {"record": f"{role}-plant-log", "segment": segment},
        "draw": draw,
        "choices": [
            {"treated": "10", "control": "10", "quota": quota}
            for quota in (low, high)
        ],
    }


MAIN_ROWS = {
    "line-a": [row("line-a", "a1", "A-low", 0, 1), row("line-a", "a2", "A-high", 0, 2)],
    "line-b": [row("line-b", "b1", "B-choice", 0, 0)],
}
SHARED_ROWS = {
    "line-a": [row("line-a", "a3", "U", 0, 1)],
    "line-b": [row("line-b", "b2", "B-gate", 0, 1)],
}


class ScriptedRandbelow:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.bounds = []

    def __call__(self, upper):
        if type(upper) is not int or upper <= 0:
            raise AssertionError(f"invalid random bound: {upper!r}")
        self.bounds.append(upper)
        try:
            answer = next(self.answers)
        except StopIteration as exc:
            raise AssertionError(f"no scripted answer for randbelow({upper})") from exc
        if type(answer) is not int or not 0 <= answer < upper:
            raise AssertionError(f"scripted answer {answer!r} outside [0, {upper})")
        return answer


def count_v1(protocol, rows, windows):
    with open_database(":memory:") as db:
        archive = IntakeArchive(db)
        journal = ReportJournal(db)
        parents = []
        with ExitStack() as stations:
            for role in ROLES:
                site = stations.enter_context(open_database(":memory:"))
                revisions = RevisionStore(site)
                issues = IssueRegister(site)
                register_protocol(revisions.registry, **protocol)
                data = RevisionInput(protocol["trial_id"], role, rows[role])
                revision = record_revision(revisions, data)
                wire = freeze_station(revisions, issues, revision.revision_id, f"{role}-v1")
                parents.append(receive_station(archive, wire).receipt_id)
        counts = []
        for lower, upper in windows:
            report, _ = publish_report(archive, journal, parents, lower, upper, 0)
            counts.append(report.result.eligible_count)
        right = archive.get_station(parents[1]).station.counts
    return tuple(counts), right


def main():
    main_counts, right = count_v1(MAIN_PROTOCOL, MAIN_ROWS, ((0, 1), (1, 3), (2, 3), (4, 4)))
    shared_counts, _ = count_v1(SHARED_PROTOCOL, SHARED_ROWS, ((0, 1), (1, 1), (2, 2)))
    if main_counts != (4, 6, 4, 0) or shared_counts != (3, 2, 0):
        raise AssertionError((main_counts, shared_counts))
    if len(right) != 1 or (right[0].public_values, right[0].quota, right[0].effect, right[0].count) != ((), 0, 0, 2):
        raise AssertionError(right)
    scripted = ScriptedRandbelow((1, 0))
    if (scripted(2), scripted(1), scripted.bounds) != (1, 0, [2, 1]):
        raise AssertionError(scripted.bounds)
    print(json.dumps({"main_eligible": main_counts, "shared_eligible": shared_counts,
                      "main_right_v1_counts": [entry.as_dict() for entry in right]}, sort_keys=True))


if __name__ == "__main__":
    main()
