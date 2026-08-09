import logging
import os

from flask import Flask, render_template

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
# Autonomous Scheduler
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

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # --------------------------------------------------------
    # Register API routes
    # --------------------------------------------------------

    app.register_blueprint(api)

    # --------------------------------------------------------
    # Frontend - Main Page
    # --------------------------------------------------------

    @app.route("/", methods=["GET"])
    def home():

        logger.info("Frontend request received: /")

        return render_template(
            "index.html",
            agent_id=AGENT_ID,
            agent_name=persona.name,
            agent_domain=persona.domain,
        )

    # --------------------------------------------------------
    # Frontend - Dashboard
    # --------------------------------------------------------

    @app.route("/dashboard", methods=["GET"])
    def dashboard():

        logger.info("Frontend request received: /dashboard")

        return render_template(
            "index.html",
            agent_id=AGENT_ID,
            agent_name=persona.name,
            agent_domain=persona.domain,
        )

    # --------------------------------------------------------
    # Health Check
    # --------------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health_check():

        return {
            "status": "ok",
            "service": "Cortex AI Autonomous Creator",
            "agentId": AGENT_ID,
            "agentName": persona.name,
            "domain": persona.domain,
            "schedulerRunning": scheduler.is_running(),
        }

    # --------------------------------------------------------
    # Debug Information
    # --------------------------------------------------------

    logger.info("==============================================")
    logger.info("Flask application created successfully.")
    logger.info("Template folder: %s", app.template_folder)
    logger.info("Static folder: %s", app.static_folder)
    logger.info("==============================================")

    logger.info("Registered Flask routes:")

    for rule in app.url_map.iter_rules():
        logger.info(
            "  %-30s -> %s",
            str(rule),
            rule.endpoint,
        )

    # --------------------------------------------------------
    # Check index.html
    # --------------------------------------------------------

    index_path = os.path.join(
        app.template_folder,
        "index.html",
    )

    if os.path.exists(index_path):
        logger.info(
            "Frontend index.html FOUND: %s",
            os.path.abspath(index_path),
        )
    else:
        logger.error(
            "Frontend index.html NOT FOUND: %s",
            os.path.abspath(index_path),
        )

    return app


# ============================================================
# Create Flask Application
# ============================================================

app = create_app()


# ============================================================
# Start Scheduler
# ============================================================

scheduler.start()


# ============================================================
# Run Flask
# ============================================================

if __name__ == "__main__":

    logger.info("==============================================")
    logger.info("Cortex AI Autonomous Creator started.")
    logger.info("Agent ID: %s", AGENT_ID)
    logger.info(
        "Scheduler running: %s",
        scheduler.is_running(),
    )
    logger.info("==============================================")

    logger.info(
        "OPEN THIS IN CHROME:"
    )

    logger.info(
        "http://127.0.0.1:5000/"
    )

    logger.info(
        "Dashboard:"
    )

    logger.info(
        "http://127.0.0.1:5000/dashboard"
    )

    logger.info(
        "Health:"
    )

    logger.info(
        "http://127.0.0.1:5000/health"
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )