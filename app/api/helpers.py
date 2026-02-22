from app.models.ticket import Ticket
from app.schemas.ticket import TicketOut
from app.services.minio_client import get_presigned_url


def ticket_to_out(ticket: Ticket) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    if ticket.attachment_key:
        out.attachment_url = get_presigned_url(ticket.attachment_key)
    if ticket.assignment:
        out.assignment.manager_name = ticket.assignment.manager.name
        out.assignment.business_unit_name = ticket.assignment.business_unit.name
    return out
