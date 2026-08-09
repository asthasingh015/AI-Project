import logging

from flask import Flask

from api.routes import api, add_post, register_agent
from brain.identity import IdentityFactory
from discovery.pipeline import DiscoveryPipeline
from publisher.engine import PublisherEngine
from publisher.scheduler import AutonomousPublisherScheduler


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("main")


# ============================================================
# Create Persona
# ============================================================

persona = IdentityFactory().generate_default_persona()

logger.info(
    "Persona created: %s | Domain: %s",
    persona.name,
    persona.domain,
)


# ============================================================
# Stable Agent ID
# ============================================================

# IMPORTANT:
# Ye ID restart ke baad change nahi hogi.
AGENT_ID = "cortex-main-agent"

logger.info("Agent ID: %s", AGENT_ID)


# ============================================================
# Register Agent with API
# ============================================================

register_agent(
    agent_id=AGENT_ID,
    name=persona.name,
    domain=persona.domain,
)


# ============================================================
# Discovery
# ============================================================

discovery = DiscoveryPipeline()


# ============================================================
# Publisher
# ============================================================

publisher = PublisherEngine(
    persona_name=persona.name,
    domain=persona.domain,
)


# ============================================================
# Discovery Callback
# ============================================================

def discover_topics():
    """
    Run discovery pipeline and return discovered topics.
    """

    result = discovery.run()

    logger.info(
        "Discovery returned %d queued topics.",
        result.queued_count,
    )

    return discovery.get_topics()


# ============================================================
# Editorial Evaluation
# ============================================================

def evaluate_topic(topic):
    """
    Decide whether a discovered topic should be published.
    """

    if not isinstance(topic, dict):
        return False

    try:
        score = float(topic.get("score", 0))
    except (TypeError, ValueError):
        return False

    # Only publish topics with score >= 50
    if score < 50:
        return False

    title = str(
        topic.get("title", "")
    ).strip()

    if not title:
        return False

    return True


# ============================================================
# Publish Callback
# ============================================================

def publish_topic(topic):
    """
    Convert a discovered topic into a feed-ready post
    and expose it through the API feed.
    """

    title = str(
        topic.get("title", "Untitled Topic")
    ).strip()

    category = str(
        topic.get("category", "Technology")
    ).strip()

    url = str(
        topic.get("url", "")
    ).strip()

    score = topic.get("score", 0)


    # --------------------------------------------------------
    # Generate editorial post
    # --------------------------------------------------------

    editorial_opinion = (
        f"Interesting development in {category}: "
        f"{title}. "
        f"This topic is worth following because it may have "
        f"broader implications for AI and technology."
    )

    rationale = (
        f"Selected automatically by Cortex AI Discovery Engine "
        f"with relevance score {score}."
    )

    sources = []

    if url:
        sources.append(url)


    # --------------------------------------------------------
    # Publish through PublisherEngine
    # --------------------------------------------------------

    post = publisher.publish(
        topic=title,
        editorial_opinion=editorial_opinion,
        rationale=rationale,
        sources=sources,
    )


    # --------------------------------------------------------
    # Add same post to API feed
    # --------------------------------------------------------

    api_post = add_post(
        agent_id=AGENT_ID,
        text=post["text"],
        rationale=post["rationale"],
        sources=post["sources"],
    )

    if api_post is None:
        logger.error(
            "Could not add post to API feed. "
            "Agent not found: %s",
            AGENT_ID,
        )
    else:
        logger.info(
            "Published topic into API feed: %s",
            title,
        )

    return post


# ============================================================
# Scheduler
# ============================================================

scheduler = AutonomousPublisherScheduler(
    agent_id=AGENT_ID,
    discover_topics=discover_topics,
    evaluate_topic=evaluate_topic,
    publish_topic=publish_topic,
    topic_key=lambda topic: (
        topic.get("url")
        or topic.get("title")
    ),
    interval_seconds=1800,
)


# ============================================================
# Flask App
# ============================================================

def create_app():

    app = Flask(__name__)

    app.register_blueprint(api)

    @app.get("/")
    def health_check():

        return {
            "status": "ok",
            "service": "Cortex AI Autonomous Creator",
            "agentId": AGENT_ID,
            "schedulerRunning": scheduler.is_running(),
        }

    return app


app = create_app()


# ============================================================
# Start Scheduler
# ============================================================

scheduler.start()


# ============================================================
# Run Flask
# ============================================================

if __name__ == "__main__":

    logger.info(
        "Cortex AI Autonomous Creator started."
    )

    logger.info(
        "Agent ID: %s",
        AGENT_ID,
    )

    logger.info(
        "Scheduler running: %s",
        scheduler.is_running(),
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )