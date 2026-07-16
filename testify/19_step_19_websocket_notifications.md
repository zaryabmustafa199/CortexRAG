# Step 19 — Real-Time Notifications (WebSocket + Redis Pub/Sub)

## What You're Building
A real-time notification gateway using FastAPI WebSockets and asynchronous Redis Pub/Sub channels. When a user connects to a workspace WebSocket endpoint, the connection is authenticated via a JWT query parameter and validated for workspace membership. The server subscribes to a specific Redis Pub/Sub channel (`cortex:notify:{workspace_id}`) and forwards processing events (such as document ingestion completions or failures) to the client immediately. It also implements an active keep-alive ping-pong mechanism to prevent proxy timeouts and clean up dead connections gracefully.

---

## Concepts Covered

| Concept | Definition | Why It Matters Here |
|---|---|---|
| **FastAPI WebSockets** | Bi-directional, persistent connection between a client browser and FastAPI server | Enables real-time document processing status pushes without the overhead of client polling |
| **Async Redis Pub/Sub** | Subscribing to Redis channels asynchronously using `redis.asyncio` | Allows multiple containerized API nodes to route notifications to the correct connected user, ensuring horizontal scalability |
| **Keep-Alive (Ping/Pong)** | Exchanging nominal frame messages to check connection viability | Prevents load balancers and reverse proxies (like Caddy/Nginx) from prematurely closing idle connections |
| **Connection Managers** | In-memory structures that track active sockets grouped by workspace | Allows server endpoints to broadcast payloads to all users connected to a specific tenant workspace |

---

## Files Created / Modified

| File | Role | Action |
|---|---|---|
| `app/api/v1/websocket.py` | Implements `ConnectionManager` and the WebSocket connection endpoint | Created |
| `app/api/v1/router.py` | Includes the new WebSocket route in the central API router registry | Modified |

---

## Engineering Standards Applied (§5)

- **Non-blocking asyncio** — The Redis subscriber listener uses `redis.asyncio` inside a background `asyncio.create_task` to ensure the event loop is never blocked.
- **Graceful Termination** — The WebSocket handler catches `WebSocketDisconnect` and runs clean-up code, discarding connection objects and cancelling the background subscriber tasks.
- **Query Parameter Auth** — JWT authentication is extracted from the handshake connection URL query parameters, aligning with browser WebSocket API constraints.

---

## How to Test This Step

To test this step, you can run a WebSocket client CLI tool (e.g. `wscat` or python `websockets`) or use Python code to simulate a connection:

```python
import asyncio
import websockets

async def test_ws():
    # Construct the WebSocket URL (token should be a valid active access token)
    url = "ws://localhost:8000/api/v1/ws/<workspace_uuid>?token=<jwt_token>"
    async with websockets.connect(url) as ws:
        print("Connected!")
        # Test keep-alive ping
        await ws.send("ping")
        resp = await ws.recv()
        print("Received:", resp) # Expected: "pong"
        
        # Keep connection open to listen for ingestion worker events
        try:
            while True:
                msg = await ws.recv()
                print("Injest Event:", msg)
        except Exception:
            pass

asyncio.run(test_ws())
```

Alternatively, publish a mock event to verify broadcasting:
```bash
# Connect to Redis container and publish
docker exec -it <redis_container> redis-cli PUBLISH "cortex:notify:<workspace_uuid>" '{"type": "DOCUMENT_READY", "document_id": "<doc_uuid>", "status": "READY"}'
```

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `4001: Authentication failed` | JWT token passed in `token` query parameter is missing, invalid, or expired | Generate a fresh JWT access token via `/auth/login` and append it as `?token=<jwt_token>` in the WebSocket URL |
| `4003: Access denied` | Authenticated user is not a member of the workspace requested | Verify user membership in the workspace table or invite the user |
| Connection closes after 60 seconds of inactivity | Proxy timeout | Ensure keep-alive pings ("ping" -> "pong") are sent by the client every 30 seconds to keep the connection active |

---

## What's Next

**Step 20** — Observability: set up structured JSON log formatting, integrate Sentry SDK error reporting, configure Prometheus metrics, and implement an extended health-check path that queries postgres, redis, and minio.
