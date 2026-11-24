from intake.pairing import resolve_pair
from report.population import iter_conditioned_allocations
from report.request import parse_report_request
from report.tail import calculate_tail


def publish_report(archive, journal, receipt_ids, quota_min, quota_max, threshold, *, before_commit=None):
    if archive.db is not journal.db:
        raise ValueError('archive and journal must use the same center connection')
    request = parse_report_request(receipt_ids, quota_min, quota_max, threshold)
    pair = resolve_pair(archive, request.receipt_ids)
    result = calculate_tail(iter_conditioned_allocations(pair, request), request.threshold)
    return journal.commit_report(request, result, before_commit=before_commit)
