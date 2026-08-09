"""
publisher/scheduler.py

Autonomous background scheduler for Cortex AI's Publisher Module.

This module is intentionally self-contained: it does not import or modify
brain/, discovery/, ai_intelligence/, api/, or main.py. Instead, it accepts
callables (dependency injection) for discovery, editorial analysis, and
publishing so it can be wired to the existing PublisherEngine and other
modules from the call site (e.g. inside publisher/engine.py or wherever
POST /api/agent/init is handled) without this file needing to know their
concrete interfaces.

Typical wiring (illustrative only -- lives in the caller, not here):

    from publisher.engine import PublisherEngine
    from publisher.scheduler import AutonomousPublisherScheduler

    engine = PublisherEngine(...)  # existing, unmodified

    scheduler = AutonomousPublisherScheduler(
        agent_id="agent-123",
        discover_topics=discovery_pipeline.get_candidates,
        evaluate_topic=lambda topic: brain_opinion.review(topic),
        publish_topic=engine.publish,
        interval_seconds=1800,
    )
    scheduler.start()
    # Flask handler for POST /api/agent/init returns immediately;
    # the loop keeps running in a daemon thread.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Set

logger = logging.getLogger("publisher.scheduler")


@dataclass
class SchedulerConfig:
    """Configuration for an AutonomousPublisherScheduler run.

    Attributes:
        interval_seconds: Delay between discovery/publishing cycles during
            normal (production-like) operation.
        startup_delay_seconds: Optional delay before the very first cycle
            runs, useful to let other init steps settle.
        max_topics_per_cycle: Safety cap on how many candidate topics are
            processed in a single cycle.
        stop_wait_timeout: Max seconds to wait for the background thread to
            join when stop() is called.
    """

    interval_seconds: float = 1800.0
    startup_delay_seconds: float = 0.0
    max_topics_per_cycle: int = 5
    stop_wait_timeout: float = 10.0


TopicId = Any  # Whatever identifier type discovery/topics use (str, int, etc.)


class AutonomousPublisherScheduler:
    """Runs an autonomous Discovery -> Editorial Judgment -> Publisher loop.

    The scheduler owns no domain logic itself. It is a thin, thread-safe
    orchestration layer that repeatedly calls injected callbacks:

        discover_topics() -> Iterable[topic]
            Returns candidate topics/articles to consider this cycle.

        evaluate_topic(topic) -> bool
            Returns True if the topic passes editorial judgment and should
            be published, False if it should be rejected.

        publish_topic(topic) -> Any
            Publishes an approved topic (e.g. via PublisherEngine.publish)
            and returns the published post (or any truthy result).

        topic_key(topic) -> Hashable, optional
            Extracts a stable identifier for a topic, used to avoid
            publishing the same topic repeatedly. Defaults to `id(topic)`
            if not provided -- callers should supply a real key (e.g. a
            URL or topic id) for correct de-duplication.

    This class does not implement editorial logic, persona logic, or
    duplicate-content detection itself -- it only orchestrates calls into
    existing modules via the callbacks above, per the "do not duplicate
    functionality" requirement.
    """

    # Class-level registry to prevent two scheduler instances from running
    # concurrently for the same agent_id (requirement: prevent multiple
    # scheduler loops accidentally starting for the same agent).
    _active_agent_ids: Set[str] = set()
    _registry_lock = threading.Lock()

    def __init__(
        self,
        agent_id: str,
        discover_topics: Callable[[], Iterable[Any]],
        evaluate_topic: Callable[[Any], bool],
        publish_topic: Callable[[Any], Any],
        topic_key: Optional[Callable[[Any], Any]] = None,
        config: Optional[SchedulerConfig] = None,
        interval_seconds: Optional[float] = None,
    ) -> None:
        """Initialize the scheduler.

        Args:
            agent_id: Unique identifier for the agent this scheduler serves.
                Used to prevent duplicate concurrent schedulers.
            discover_topics: Zero-arg callable returning candidate topics.
            evaluate_topic: Callable(topic) -> bool, editorial judgment.
            publish_topic: Callable(topic) -> Any, performs the publish.
            topic_key: Optional callable(topic) -> hashable key, used for
                de-duplication. Falls back to `id(topic)` if omitted.
            config: Optional SchedulerConfig. If omitted, a default config
                is built (optionally overridden by interval_seconds).
            interval_seconds: Convenience shortcut to set the cycle
                interval without constructing a SchedulerConfig. Useful for
                tests that want a very small interval.
        """
        if not agent_id:
            raise ValueError("agent_id is required")

        self.agent_id = agent_id
        self._discover_topics = discover_topics
        self._evaluate_topic = evaluate_topic
        self._publish_topic = publish_topic
        self._topic_key = topic_key or (lambda t: id(t))

        self.config = config or SchedulerConfig()
        if interval_seconds is not None:
            self.config.interval_seconds = interval_seconds

        self._published_keys: Set[Any] = set()
        self._state_lock = threading.Lock()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        self._run_id = str(uuid.uuid4())

    # ------------------------------------------------------------------ #
    # Public control API
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the autonomous publishing loop in a daemon background thread.

        Safe to call once per agent. If a scheduler is already running for
        this agent_id (in this process), this is a no-op that logs a
        warning instead of starting a second loop.
        """
        with self._state_lock:
            if self._running:
                logger.warning(
                    "Scheduler already running for agent_id=%s; ignoring start()",
                    self.agent_id,
                )
                return

            with AutonomousPublisherScheduler._registry_lock:
                if self.agent_id in AutonomousPublisherScheduler._active_agent_ids:
                    logger.warning(
                        "Another scheduler instance is already active for "
                        "agent_id=%s; refusing to start a second loop",
                        self.agent_id,
                    )
                    return
                AutonomousPublisherScheduler._active_agent_ids.add(self.agent_id)

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name=f"publisher-scheduler-{self.agent_id}",
                daemon=True,
            )
            self._thread.start()

        logger.info(
            "Scheduler started for agent_id=%s (interval=%.1fs, run_id=%s)",
            self.agent_id,
            self.config.interval_seconds,
            self._run_id,
        )

    def stop(self) -> None:
        """Signal the loop to stop and wait for the background thread to exit.

        Safe to call multiple times and safe to call even if the scheduler
        was never started.
        """
        with self._state_lock:
            if not self._running:
                logger.info(
                    "stop() called for agent_id=%s but scheduler was not running",
                    self.agent_id,
                )
                return
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=self.config.stop_wait_timeout)

        with self._state_lock:
            self._running = False
            self._thread = None

        with AutonomousPublisherScheduler._registry_lock:
            AutonomousPublisherScheduler._active_agent_ids.discard(self.agent_id)

        logger.info("Scheduler stopped for agent_id=%s", self.agent_id)

    def is_running(self) -> bool:
        """Return True if the background publishing loop is currently active."""
        with self._state_lock:
            return self._running

    # ------------------------------------------------------------------ #
    # Internal loop / cycle logic
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        """Background thread target: repeatedly run cycles until stopped."""
        if self.config.startup_delay_seconds > 0:
            self._stop_event.wait(self.config.startup_delay_seconds)

        while not self._stop_event.is_set():
            try:
                self._run_cycle()
            except Exception:  # noqa: BLE001 - must never kill the loop
                logger.exception(
                    "Publishing cycle failed for agent_id=%s; will retry next cycle",
                    self.agent_id,
                )

            # Wait for the configured interval, but wake immediately if
            # stop() is called during the wait.
            self._stop_event.wait(self.config.interval_seconds)

        with self._state_lock:
            self._running = False

    def _run_cycle(self) -> None:
        """Execute a single Discovery -> Editorial Judgment -> Publisher cycle."""
        logger.info("Discovery cycle started for agent_id=%s", self.agent_id)

        try:
            candidates = list(self._discover_topics() or [])
        except Exception:
            logger.exception(
                "Topic discovery failed for agent_id=%s; skipping this cycle",
                self.agent_id,
            )
            return

        processed = 0
        for topic in candidates:
            if processed >= self.config.max_topics_per_cycle:
                break

            try:
                key = self._topic_key(topic)
            except Exception:
                logger.exception(
                    "Failed to compute topic key for agent_id=%s; skipping topic",
                    self.agent_id,
                )
                continue

            with self._state_lock:
                already_published = key in self._published_keys

            if already_published:
                logger.debug(
                    "Skipping already-published topic key=%s for agent_id=%s",
                    key,
                    self.agent_id,
                )
                continue

            processed += 1
            self._process_topic(topic, key)

    def _process_topic(self, topic: Any, key: Any) -> None:
        """Run editorial judgment on one topic, then publish it if approved."""
        try:
            approved = bool(self._evaluate_topic(topic))
        except Exception:
            logger.exception(
                "Editorial evaluation failed for agent_id=%s, topic_key=%s; "
                "treating as rejected",
                self.agent_id,
                key,
            )
            approved = False

        if not approved:
            logger.info(
                "Topic rejected for agent_id=%s, topic_key=%s",
                self.agent_id,
                key,
            )
            return

        try:
            self._publish_topic(topic)
        except Exception:
            logger.exception(
                "Publishing failed for agent_id=%s, topic_key=%s",
                self.agent_id,
                key,
            )
            return

        with self._state_lock:
            self._published_keys.add(key)

        logger.info(
            "Topic published for agent_id=%s, topic_key=%s",
            self.agent_id,
            key,
        )