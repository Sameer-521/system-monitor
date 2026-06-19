import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status

from app.shared import latest_snapshot, client_subs, sub_lock
from app.pubsub import broadcast, poller
from app.schema import Register
from app.settings import _settings
from app.routers import metrics

# TODO: add logging and replace print statements


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks = [
        asyncio.create_task(poller(latest_snapshot)),
        asyncio.create_task(broadcast(latest_snapshot, client_subs, sub_lock)),
    ]
    print("Tasks created succesfully...")
    yield

    print("Initiating graceful shutdown for all tasks...")
    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("All background tasks closed safely.")


app = FastAPI(lifespan=lifespan)
app.state.clients = set(["Sameer", "John", "Joe"])

app.include_router(metrics.metrics_router)


@app.get("/")
async def root():
    return {"response": "This is the root page"}


@app.post("/register", status_code=201)
async def register(request: Request, user: Register):
    username: str = user.model_dump().get("username", "")
    if username in request.app.state.clients:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"error": "user already exists"}
        )
    request.app.state.clients.add(username)
    print(f"Client: {username}")
