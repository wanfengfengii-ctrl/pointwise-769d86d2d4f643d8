import json

from intake.executable_pairing import resolve_executable_pair
from issue.executable import encode_segment
from report.coupling import require_randbelow, reissue_choice
from report.executable_population import enumerate_complete_allocations, find_complete_allocation
from report.ticket_journal import parent_entry, parse_window
from storage import database_id


def _ticket_segments(pair, complete):
    return [
        json.loads(encode_segment(pair.first.issue_id, complete.left.allocation_id)),
        json.loads(encode_segment(pair.second.issue_id, complete.right.allocation_id)),
    ]


def _build_payload(pair, complete, quota_min, quota_max, initial_ticket_id, kept):
    parents = [parent_entry(pair.first_archived), parent_entry(pair.second_archived)]
    segments = None if complete is None else _ticket_segments(pair, complete)
    return {
        'ticket_id': None,
        'initial_ticket_id': initial_ticket_id,
        'parents': parents,
        'quota_min': quota_min,
        'quota_max': quota_max,
        'segments': segments,
        'kept': kept,
    }


def _materialize(journal, payload, *, before_commit):
    ticket_id = journal.commit_ticket(payload, before_commit=before_commit)
    result = dict(payload)
    result['ticket_id'] = ticket_id
    return result


def draw_ticket(archive, journal, receipt_ids, quota_min, quota_max, randbelow, *, before_commit=None):
    if archive.db is not journal.db:
        raise ValueError('archive and journal must use the same center connection')
    require_randbelow(randbelow)
    lower, upper = parse_window(quota_min, quota_max)
    pair = resolve_executable_pair(archive, receipt_ids)
    population = enumerate_complete_allocations(pair, lower, upper)
    if not population:
        complete = None  # empty population: no extraction callback is invoked
    else:
        index = randbelow(len(population))
        if type(index) is not int or not 0 <= index < len(population):
            raise ValueError('randbelow returned a value outside [0, n)')
        complete = population[index]
    payload = _build_payload(pair, complete, lower, upper, None, None)
    return _materialize(journal, payload, before_commit=before_commit)


def _load_initial(journal, initial_ticket_id):
    database_id(initial_ticket_id, 'initial ticket id')
    raw = journal.get_ticket_payload(initial_ticket_id)
    if raw is None:
        raise KeyError(f'unknown ticket {initial_ticket_id}')
    initial = json.loads(raw)
    if initial['initial_ticket_id'] is not None:
        raise ValueError('a reissue ticket cannot itself be reissued')
    if initial['segments'] is None:
        raise ValueError('initial ticket has no executable ticket segments')
    return initial


def reissue_ticket(archive, journal, initial_ticket_id, quota_min, quota_max, randbelow,
                   *, before_commit=None):
    if archive.db is not journal.db:
        raise ValueError('archive and journal must use the same center connection')
    require_randbelow(randbelow)
    lower, upper = parse_window(quota_min, quota_max)
    initial = _load_initial(journal, initial_ticket_id)
    existing = journal.get_reissue(initial_ticket_id)
    if existing is not None:
        reissue_id, old_lower, old_upper = existing
        if (old_lower, old_upper) != (lower, upper):
            raise ValueError('the initial ticket already reissued under another quota window')
        saved = journal.get_ticket_payload(reissue_id)
        return _with_id(reissue_id, json.loads(saved))
    receipt_ids = tuple(parent['receipt_id'] for parent in initial['parents'])
    pair = resolve_executable_pair(archive, receipt_ids)
    old_population = enumerate_complete_allocations(
        pair, initial['quota_min'], initial['quota_max'])
    new_population = enumerate_complete_allocations(pair, lower, upper)
    initial_complete = find_complete_allocation(
        old_population,
        initial['segments'][0]['allocation_id'],
        initial['segments'][1]['allocation_id'])
    if initial_complete is None:
        raise ValueError('initial ticket segments do not resolve to a stored allocation')
    if not new_population:
        complete, kept = None, False
    else:
        complete, kept = reissue_choice(
            randbelow, old_population, new_population, initial_complete)
    payload = _build_payload(pair, complete, lower, upper, initial_ticket_id, kept)
    return _materialize(journal, payload, before_commit=before_commit)


def _with_id(ticket_id, payload):
    result = dict(payload)
    result['ticket_id'] = ticket_id
    return result
