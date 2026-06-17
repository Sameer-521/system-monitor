Client                  FastAPI Server (Auth)         FastAPI Server (Stream)
  |                              |                              |
  | 1. POST /stream/ticket ------->|                              |
  |    (With Bearer Token)       |                              |
  |                              |                              |
  |<-- 2. Returns ticket_id -----|                              |
  |    (UUID, valid for 5-10s)   |                              |
  |                              |                              |
  | 3. Connect to SSE: /stream?ticket=ticket_id ---------------->|
  |                                                             | 4. Validate & consume ticket.
  |                                                             |    Map connection to Client object.
  |<-- 5. Establish SSE Stream ---------------------------------|