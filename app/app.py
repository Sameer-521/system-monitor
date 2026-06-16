from fastapi import FastAPI, HTTPException, status
from fastapi.sse import EventSourceResponse

from app.data import SYSTEM_DATA
from app.schema import Register

app = FastAPI()

clients = set()


@app.post("/register", status_code=201)
async def register(user: Register):
    username = user.model_dump().get("username")
    if username in clients:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "user already exists"}
        )
    clients.add(username)
    print(f"Client: {username}")


@app.get("/stream/all", response_class=EventSourceResponse)
async def stream_all():
    for name, stat in SYSTEM_DATA.items():
        yield {name: stat}
