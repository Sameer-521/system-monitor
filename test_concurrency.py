import asyncio
import json
import os
import sys
from typing import Optional

import httpx

BASE_URL = "http://127.0.0.1:8000/metrics"
ENABLE_DELAY = False
DELAY_SECONDS = 2
DURATION = 15

USERS = [
    {
        "name": "Sameer",
        "params": "cpu=true&memory=true&disk=true",
        "outfile": "sameer_stream.jsonl",
    },
    {
        "name": "John",
        "params": "cpu=true&memory=true",
        "outfile": "john_stream.jsonl",
    },
    {
        "name": "Joe",
        "params": "memory=true&disk=true",
        "outfile": "joe_stream.jsonl",
    },
]


async def issue_ticket(client: httpx.AsyncClient, user: str) -> Optional[str]:
    url = f"{BASE_URL}/stream/ticket/{user}"
    try:
        resp = await client.post(url)
        resp.raise_for_status()
        data = resp.json()
        ticket_id = data["ticket"]["id"]
        print(f"{user}'s ticket: {ticket_id}")
        return ticket_id
    except httpx.HTTPStatusError as e:
        print(f"ERROR: Failed to get ticket for {user}: HTTP {e.response.status_code}")
    except (httpx.RequestError, json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: Failed to get ticket for {user}: {e}")
    return None


async def stream_user(
    client: httpx.AsyncClient,
    user: str,
    ticket: str,
    params: str,
    outfile: str,
    done: asyncio.Event,
):
    url = f"{BASE_URL}/stream/{user}?{params}"
    headers = {
        "Accept": "text/event-stream",
        "x-ticket": ticket,
    }
    try:
        async with client.stream("GET", url, headers=headers, timeout=None) as resp:
            resp.raise_for_status()
            with open(outfile, "w") as fh:
                async for line in resp.aiter_lines():
                    if done.is_set():
                        break
                    if line.startswith("data: "):
                        payload = line.removeprefix("data: ")
                        try:
                            json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        fh.write(payload + "\n")
    except httpx.HTTPStatusError as e:
        print(f"ERROR: Stream for {user} failed with HTTP {e.response.status_code}")
    except (httpx.RequestError, OSError) as e:
        if not done.is_set():
            print(f"ERROR: Stream for {user} connection error: {e}")
    except Exception as e:
        if not done.is_set():
            print(f"ERROR: Unexpected error in stream for {user}: {e}")
    finally:
        done.set()


def report_counts():
    print()
    print("=== Done ===")
    for user in USERS:
        outfile = user["outfile"]
        name = user["name"]
        if os.path.isfile(outfile):
            with open(outfile) as fh:
                count = sum(1 for _ in fh)
            print(f"{name} stream events: {count}")
        else:
            print(f"{name} stream events: 0 (no output file)")
    print("Output saved to: " + ", ".join(u["outfile"] for u in USERS))


async def main():
    print("=== Issuing tickets ===")

    async with httpx.AsyncClient() as client:
        tickets = await asyncio.gather(
            *(issue_ticket(client, u["name"]) for u in USERS)
        )

    if any(t is None for t in tickets):
        print("ERROR: One or more tickets could not be obtained. Aborting.")
        return

    parsed_tickets: list[str] = [t for t in tickets if t is not None]

    print("=== Streaming for 15 seconds... ===")
    done = asyncio.Event()

    async with httpx.AsyncClient() as client:
        tasks = []
        for user_cfg, ticket in zip(USERS, parsed_tickets):
            tasks.append(
                asyncio.create_task(
                    stream_user(
                        client,
                        user_cfg["name"],
                        ticket,
                        user_cfg["params"],
                        user_cfg["outfile"],
                        done,
                    )
                )
            )
            if ENABLE_DELAY:
                print(f"Delaying {DELAY_SECONDS} seconds before next worker...")
                await asyncio.sleep(DELAY_SECONDS)

        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=DURATION)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"ERROR: Unexpected gather error: {e}")
        finally:
            done.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    report_counts()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
