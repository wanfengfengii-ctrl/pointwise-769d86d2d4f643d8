from dataclasses import dataclass

from intake.archive import ArchivedStation
from report.journal import ReportReceipt, ReportRecord


@dataclass(frozen=True)
class HistoricalReport:
    record: ReportRecord
    parents: tuple[ArchivedStation, ArchivedStation]
    receipt: ReportReceipt


def get_report(archive, journal, report_id):
    if archive.db is not journal.db:
        raise ValueError('archive and journal must use the same center connection')
    saved = journal.load_report(report_id)
    if saved is None:
        return None
    record, receipt = saved
    parents = tuple(archive.get_station(receipt_id) for receipt_id in record.request.receipt_ids)
    return HistoricalReport(record, parents, receipt)
