import json

from storage import database_id


def get_ticket(archive, journal, ticket_id):
    if archive.db is not journal.db:
        raise ValueError('archive and journal must use the same center connection')
    database_id(ticket_id, 'ticket id')
    raw = journal.get_ticket_payload(ticket_id)
    if raw is None:
        return None
    ticket = json.loads(raw)
    ticket['ticket_id'] = ticket_id
    return ticket
