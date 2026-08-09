from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from flask import Blueprint, jsonify, request


# ============================================================
# API Blueprint
# ============================================================

api = Blueprint(
    "api",
    __name__,
    url_prefix="/api",
)


# ============================================================
# In-memory agent storage
# ============================================================

_agents = {}
_agents_lock = Lock()


# ============================================================
# Utility functions
# ============================================================

def _utc_iso():
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_post_id():
    """Create a short unique post ID."""
    return "p-" + uuid4().hex[:12]


# ============================================================
# Register agent internally from main.py
# ============================================================

def register_agent(agent_id, name, domain):
    """
    Register or reset an agent in the internal API store.
    """

    with _agents_lock:
        _agents[agent_id] = {
            "agent_id": agent_id,
            "persona": {
                "name": str(name),
                "domain": str(domain),
            },
            "initialized_at": _utc_iso(),
            "posts": [],
        }

        return _agents[agent_id]


# ============================================================
# POST /api/agent/init
# ============================================================

@api.post("/agent/init")
def initialize_agent():
    """
    Initialize a new agent from frontend/API request.
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

    name = str(
        persona.get("name", "")
    ).strip()

    domain = str(
        persona.get("domain", "")
    ).strip()

    if not name:
        return jsonify({
            "error": "Persona name is required."
        }), 400

    if not domain:
        return jsonify({
            "error": "Persona domain is required."
        }), 400

    agent_id = str(uuid4())

    register_agent(
        agent_id=agent_id,
        name=name,
        domain=domain,
    )

    return jsonify({
        "agentId": agent_id,
        "name": name,
        "domain": domain,
    }), 201


# ============================================================
# GET /api/agent/feed
# ============================================================

@api.get("/agent/feed")
def get_agent_feed():
    """
    Return posts for a specific agent.
    """

    agent_id = request.args.get(
        "agentId",
        ""
    ).strip()

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

    posts.sort(
        key=lambda post: post.get(
            "createdAt",
            ""
        ),
        reverse=True,
    )

    return jsonify({
        "agentId": agent_id,
        "posts": posts,
    }), 200


# ============================================================
# GET /api/agent
# ============================================================

@api.get("/agent")
def get_agent():
    """
    Return agent information.
    """

    agent_id = request.args.get(
        "agentId",
        ""
    ).strip()

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

        return jsonify({
            "agentId": agent["agent_id"],
            "persona": agent["persona"],
            "initializedAt": agent["initialized_at"],
            "postCount": len(agent["posts"]),
        }), 200


# ============================================================
# Add published post to API feed
# ============================================================

def add_post(
    agent_id,
    text,
    rationale,
    sources=None,
):
    """
    Add a published post to an agent's feed.
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