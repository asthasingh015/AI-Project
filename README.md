# Cortex AI — Publisher Module

> **"Not an AI Writer. An AI Technology Thinker."**

The **Autonomous Publishing Module** for the Cortex AI project. It consumes an
**approved topic** from the Discovery layer and a **persona** from the Brain
layer (`brain/`), enqueues the topic, generates a LinkedIn-style technology
post with a rationale and sources, and persists it — fully autonomously.

This module deliberately contains **no** topic discovery, crawling, ranking,
persona creation, memory, or opinion-engine logic. Those live in `brain/` and
the Discovery layer. Everything here is limited to the publishing workflow.

## Features

- FastAPI backend (`GET /`, `GET /health`, feed, dashboard, stats, publish).
- APScheduler runs the publishing workflow on an interval (default 30 min).
- OpenAI (primary) with automatic Gemini fallback — or Gemini alone.
- **Publish queue**: approved topics are enqueued as `pending` and drained by
  the scheduler, instead of being published immediately.
- **Retry system**: a failed queue item is retried up to 3 times with backoff
  before being marked `failed`.
- Central pipeline lives in `publisher/services/publisher.py` and is shared by
  the scheduler and the manual `POST /api/publish` endpoint (no duplication).
- SQLite + async SQLAlchemy, structured logging with secret redaction, Docker.

## Architecture

```text
                APScheduler (every N minutes)
                        │
                        ▼
              Discovery / Member 2 API   GET /api/topics/approved
                        │
                        ▼
                 Publish Queue (pending)
                        │
                        ▼
              Brain / Member 1 API       GET /api/persona
                        │
                        ▼
                 AI Generator            OpenAI -> Gemini fallback
                        │
                        ▼
               SQLite (posts table)      published (3-attempt retry)
                        │
                        ▼
                   Feed API
```

## Installation

Requires Python 3.12+.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Environment Variables

Copy the template and fill in your values:

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `Cortex AI Publisher` | Service name |
| `APP_VERSION` | `1.0.0` | Service version |
| `ENVIRONMENT` | `development` | Runtime environment |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/cortex_publisher.db` | Database location |
| `OPENAI_API_KEY` | *(empty)* | OpenAI key (primary provider) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `GEMINI_API_KEY` | *(empty)* | Gemini key (fallback / sole provider) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `MEMBER1_PERSONA_URL` | `http://localhost:8002/api/persona` | Brain / Member 1 persona endpoint |
| `MEMBER2_TOPICS_URL` | `http://localhost:8001/api/topics/approved` | Discovery / Member 2 topics endpoint |
| `SCHEDULER_ENABLED` | `true` | Turn the scheduler on/off |
| `SCHEDULER_INTERVAL_MINUTES` | `30` | Publish interval |
| `QUEUE_BATCH_SIZE` | `5` | Max topics enqueued per cycle |
| `PUBLICATION_BATCH_SIZE` | `1` | Max posts published per cycle |
| `PUBLISH_MAX_ATTEMPTS` | `3` | Retry attempts before failure |
| `RETRY_BACKOFF_SECONDS` | `60` | Base backoff per attempt |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Outbound HTTP timeout |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `LOG_FILE` | `logs/publisher.log` | Log file path |

## Running

```bash
uvicorn main:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`.

## Running with Docker

```bash
docker build -t cortex-publisher .
docker run --env-file .env -p 8000:8000 cortex-publisher
```

Mount volumes for persistence in production:
`-v cortex_data:/app/data -v cortex_logs:/app/logs`.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Health / status |
| `GET` | `/health` | Detailed health (`{"status":"running", ...}`) |
| `GET` | `/api/agent/feed` | Published posts, newest first |
| `GET` | `/api/dashboard` | Totals + scheduler + queue status |
| `GET` | `/api/stats` | `{published, pending, failed}` counts |
| `POST` | `/api/publish` | Manual publish (same pipeline as scheduler) |

### `GET /api/agent/feed`

```json
{
  "total": 1,
  "posts": [
    {
      "id": 1,
      "title": "The Future of AI Agents",
      "text": "AI agents are becoming...",
      "rationale": "This topic...",
      "sources": ["https://example.com/source"],
      "status": "published",
      "attempts": 1,
      "created_at": "2026-08-08T14:30:00Z",
      "published_at": "2026-08-08T14:30:00Z"
    }
  ]
}
```

### `GET /api/stats`

```json
{ "published": 12, "pending": 3, "failed": 1, "total": 16 }
```

## Scheduler

APScheduler (`AsyncIOScheduler`) starts with the FastAPI lifespan and stops
gracefully on shutdown. The job is interval-triggered, reads
`SCHEDULER_INTERVAL_MINUTES` from the environment, and uses
`max_instances=1`, `coalesce=True`, and a `misfire_grace_time` of 600s so
publishing cycles never overlap. Set `SCHEDULER_ENABLED=false` to disable.

## Database

SQLite database at `DATABASE_URL`. The `posts` table acts as the publish
queue:

`id`, `title`, `description`, `text`, `rationale`, `sources` (JSON text),
`status` (`pending` / `published` / `failed`), `attempts`, `last_error`,
`created_at`, `published_at`, `next_retry_at`.

Tables are created automatically on startup. Transactions are committed per
queue item and rolled back on failure.

## AI Provider Configuration

```text
OPENAI_API_KEY present
        ├─ use OpenAI
        └─ OpenAI fails -> use Gemini (if configured)
Only GEMINI_API_KEY -> use Gemini
Neither set         -> ProviderConfigurationError (clear, logged, no keys leaked)
```

The AI must return JSON with `text`, `rationale`, and `sources`. Output is
validated, markdown fences are stripped, and only real `http(s)` source URLs
are kept — upstream-supplied URLs are always preferred, never invented.

## Integration Contracts

### Brain / Member 1 — `GET /api/persona`

```json
{
  "persona": {
    "name": "Nova",
    "role": "AI Technology Thinker",
    "tone": "analytical",
    "style": "concise and insightful",
    "values": ["technical accuracy", "innovation", "practical thinking"],
    "opinions": ["AI should augment human reasoning"]
  }
}
```

Flat payloads without the `persona` wrapper are also accepted.

### Discovery / Member 2 — `GET /api/topics/approved`

```json
{
  "topic": {
    "title": "AI Agents in Software Development",
    "description": "How autonomous coding agents are changing software development.",
    "sources": ["https://example.com/article"]
  }
}
```

Variations (`{"topics": [...]}` or a flat `{"title": ...}`) are accepted. If no
approved topic exists, the cycle logs the condition and ends normally — no
empty post is enqueued.

## Testing the Manual Publish Endpoint

```bash
curl -X POST http://localhost:8000/api/publish
curl http://localhost:8000/api/agent/feed
curl http://localhost:8000/api/dashboard
curl http://localhost:8000/api/stats
```

`POST /api/publish` reuses the exact same pipeline as the scheduler.

## Production Considerations

- Set `ENVIRONMENT=production` and `LOG_LEVEL=INFO`.
- Provide real AI keys via secrets/`--env-file`; never commit `.env`.
- Add auth in front of `POST /api/publish` if exposed publicly.
- Mount persistent volumes for `/app/data` and `/app/logs`.
- Point `MEMBER1_PERSONA_URL` / `MEMBER2_TOPICS_URL` at deployed services.
- Run behind a reverse proxy (nginx/Traefik) with HTTPS.
