from typing import Annotated
import time
from dataclasses import dataclass
from uuid import uuid4
from fastapi import HTTPException, Header, status

from app.schema import TicketHeader


@dataclass(frozen=True)
class Ticket:
    id: str
    issued_at: float
    claims: dict[str, str]


class TicketStore:
    def __init__(self, lifetime: int = 30) -> None:
        self._tickets: dict[str, Ticket] = {}
        self.ticket_lifetime = lifetime

    def issue(self, client_id: str) -> Ticket:
        ticket_id = str(uuid4())
        curr_time = time.monotonic()
        claims = {"client_id": client_id}
        ticket = Ticket(ticket_id, curr_time, claims)
        self._tickets[ticket_id] = ticket
        return ticket

    def consume(self, ticket_id) -> bool:
        """Returns True if ticket was valid and consumed succesfully else False"""
        curr_time = time.monotonic()
        ticket = self._tickets.get(ticket_id, None)

        if ticket and (curr_time - ticket.issued_at) <= self.ticket_lifetime:
            self._tickets.pop(ticket_id)
            # print("Valid")
            return True

        # print("Invalid")
        return False

    async def verify_ticket_header(self, ticket: Annotated[TicketHeader, Header()]):
        ticket = ticket.model_dump().get("x_ticket", "")
        if not self.consume(ticket):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid ticket"},
            )
        return ticket
