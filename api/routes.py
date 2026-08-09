"""
Cortex AI Autonomous Creator - API Routes

Required endpoints:
POST /api/agent/init
GET  /api/agent/feed?agentId=<agent_id>
"""

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from flask import Blueprint, jsonify, request


api = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# In-memory agent state
# ---------------------------------------------------------------------------

_agents = {}
_agents_lock = Lock()


def _utc_now():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _utc_iso():
    """Return current UTC timestamp in ISO-8601 format."""
    return _utc_now().isoformat().replace("+00:00", "Z")


def _create_agent_id():
    """Create a unique agent ID."""
    return str(uuid4())


def _create_post_id():
    """Create a unique post ID."""
    return "p-" + uuid4().hex[:12]


# ---------------------------------------------------------------------------
# POST /api/agent/init
# ---------------------------------------------------------------------------

@api.post("/agent/init")
def initialize_agent():
    """
    Initialize the autonomous AI persona.

    Expected request:

    {
        "persona": {
            "name": "Ada",
            "domain": "AI Security"
        }
    }

    Response:

    {
        "agentId": "..."
    }
    """

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Request body must be valid JSON."
        }), 400

    persona = data.get("persona")

    if not isinstance(persona, dict):
        return jsonify({
            "error": "Missing 'persona' object."
        }), 400

    name = str(persona.get("name", "")).strip()
    domain = str(persona.get("domain", "")).strip()

    if not name:
        return jsonify({
            "error": "Persona name is required."
        }), 400

    if not domain:
        return jsonify({
            "error": "Persona domain is required."
        }), 400

    agent_id = _create_agent_id()

    with _agents_lock:
        _agents[agent_id] = {
            "agent_id": agent_id,
            "persona": {
                "name": name,
                "domain": domain,
            },
            "initialized_at": _utc_iso(),
            "posts": [],
        }

    return jsonify({
        "agentId": agent_id
    }), 201


# ---------------------------------------------------------------------------
# GET /api/agent/feed
# ---------------------------------------------------------------------------

@api.get("/agent/feed")
def get_agent_feed():
    """
    Return the autonomous agent feed.

    Example:

    GET /api/agent/feed?agentId=abc-123
    """

    agent_id = request.args.get("agentId", "").strip()

    if not agent_id:
        return jsonify({
            "error": "agentId query parameter is required."
        }), 400

    with _agents_lock:
        agent = _agents.get(agent_id)

        if agent is None:
            return jsonify({
                "error": "Agent not found."
            }), 404

        posts = list(agent["posts"])

    # Newest post first.
    posts.sort(
        key=lambda post: post.get("createdAt", ""),
        reverse=True
    )

    return jsonify({
        "posts": posts
    }), 200


# ---------------------------------------------------------------------------
# Development helper
# ---------------------------------------------------------------------------

def add_post(
    agent_id,
    text,
    rationale,
    sources,
):
    """
    Add a generated post to an initialized agent.

    This helper will later be called by the autonomous publishing engine.
    """

    with _agents_lock:
        agent = _agents.get(agent_id)

        if agent is None:
            return None

        post = {
            "id": _create_post_id(),
            "createdAt": _utc_iso(),
            "text": str(text),
            "rationale": str(rationale),
            "sources": list(sources or []),
        }

        agent["posts"].append(post)

        return post
    