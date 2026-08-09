/**
 * Cortex AI Autonomous Creator — frontend logic.
 *
 * Uses the real Flask API.
 * No mock/fake posts are generated.
 */

(() => {
  "use strict";

  // ------------------------------------------------------------------
  // Config
  // ------------------------------------------------------------------

  // Same Flask server se API call hogi.
  // Isliye http://127.0.0.1:5000 likhne ki zarurat nahi.
  const API_BASE = "";

  const AGENT_ID = "cortex-main-agent";

  const FEED_URL =
    `${API_BASE}/api/agent/feed?agentId=${encodeURIComponent(AGENT_ID)}`;

  const HEALTH_URL = `${API_BASE}/health`;

  const AUTO_REFRESH_MS = 30000;
  const PIPELINE_CYCLE_MS = 2600;

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------

  const el = {
    navStatusDot: document.getElementById("navStatusDot"),
    navStatusText: document.getElementById("navStatusText"),
    refreshBtn: document.getElementById("refreshBtn"),

    metricDiscovered: document.getElementById("metricDiscovered"),
    metricEvaluated: document.getElementById("metricEvaluated"),
    metricPublished: document.getElementById("metricPublished"),

    statusApi: document.getElementById("statusApi"),
    statusApiVal: document.getElementById("statusApiVal"),

    statusDiscovery: document.getElementById("statusDiscovery"),
    statusDiscoveryVal: document.getElementById("statusDiscoveryVal"),

    statusPublisher: document.getElementById("statusPublisher"),
    statusPublisherVal: document.getElementById("statusPublisherVal"),

    statusAgent: document.getElementById("statusAgent"),
    statusAgentVal: document.getElementById("statusAgentVal"),

    analyticsDiscovered: document.getElementById("analyticsDiscovered"),
    analyticsPublished: document.getElementById("analyticsPublished"),
    analyticsAvgScore: document.getElementById("analyticsAvgScore"),
    analyticsLast: document.getElementById("analyticsLast"),

    feedContent: document.getElementById("feedContent"),
    feedCount: document.getElementById("feedCount"),

    pipelineSteps: Array.from(
      document.querySelectorAll(".pipeline__step")
    ),
  };

  // ------------------------------------------------------------------
  // Utilities
  // ------------------------------------------------------------------

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function formatTimestamp(iso) {
    if (!iso) return "Unknown time";

    const date = new Date(iso);

    if (Number.isNaN(date.getTime())) {
      return String(iso);
    }

    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) {
      return "Just now";
    }

    if (diffMin < 60) {
      return `${diffMin}m ago`;
    }

    const diffHr = Math.floor(diffMin / 60);

    if (diffHr < 24) {
      return `${diffHr}h ago`;
    }

    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function relevanceTier(post) {
    const raw =
      post.relevanceScore ??
      post.relevance_score ??
      post.score ??
      post.relevance;

    if (raw == null || Number.isNaN(Number(raw))) {
      return null;
    }

    const score = Number(raw);

    const normalized =
      score > 1 ? score / 100 : score;

    if (normalized >= 0.7) {
      return {
        label: "HIGH",
        tier: "high",
      };
    }

    if (normalized >= 0.4) {
      return {
        label: "MEDIUM",
        tier: "medium",
      };
    }

    return {
      label: "LOW",
      tier: "low",
    };
  }

  function animateCounter(node, target) {
    if (!node) return;

    const start =
      parseInt(node.textContent, 10) || 0;

    const end =
      Number(target) || 0;

    if (start === end) {
      node.textContent = String(end);
      return;
    }

    const duration = 600;
    const startTime = performance.now();

    function tick(now) {
      const progress =
        Math.min(
          (now - startTime) / duration,
          1
        );

      const eased =
        1 - Math.pow(1 - progress, 3);

      const value =
        Math.round(
          start +
          (end - start) * eased
        );

      node.textContent = String(value);

      if (progress < 1) {
        requestAnimationFrame(tick);
      }
    }

    requestAnimationFrame(tick);
  }

  // ------------------------------------------------------------------
  // Feed rendering
  // ------------------------------------------------------------------

  function renderSkeleton() {
    if (!el.feedContent) return;

    el.feedContent.innerHTML = `
      <div class="skeleton-group">
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
      </div>
    `;
  }

  function renderEmptyState() {
    if (!el.feedContent) return;

    el.feedContent.innerHTML = `
      <div class="state-panel">
        <div class="state-panel__icon">◌</div>

        <h4>No intelligence published yet</h4>

        <p>
          Cortex is discovering and evaluating topics.
          Approved posts will appear here automatically.
        </p>
      </div>
    `;

    if (el.feedCount) {
      el.feedCount.textContent = "";
    }
  }

  function renderErrorState(message) {
    if (!el.feedContent) return;

    el.feedContent.innerHTML = `
      <div class="state-panel is-error">
        <div class="state-panel__icon">⚠</div>

        <h4>Feed unavailable</h4>

        <p>
          ${escapeHtml(message)}
        </p>
      </div>
    `;

    if (el.feedCount) {
      el.feedCount.textContent = "";
    }
  }

  function renderPostCard(post, index) {
    const text =
      post.text ?? "";

    const rationale =
      post.rationale ??
      "No rationale provided.";

    const sources =
      Array.isArray(post.sources)
        ? post.sources
        : [];

    const createdAt =
      post.createdAt ??
      post.created_at ??
      null;

    // First sentence/line becomes title.
    const rawTitle =
      (
        text
          .split(/\n|(?<=[.!?])\s/)[0] ||
        ""
      ).trim();

    const title =
      rawTitle ||
      "Untitled intelligence";

    const bodyText =
      rawTitle && rawTitle !== text
        ? text.slice(rawTitle.length).trim()
        : text;

    const relevance =
      relevanceTier(post);

    const cardTierClass =
      relevance
        ? ` post-card--${relevance.tier}`
        : "";

    const sourceLinks =
      sources
        .filter(Boolean)
        .map((src, i) => {
          const safeUrl =
            escapeHtml(src);

          return `
            <a
              class="post-card__source"
              href="${safeUrl}"
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
              >
                <path
                  d="M14 4h6v6M20 4l-9 9M9 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>

              Source ${sources.length > 1 ? i + 1 : ""}
            </a>
          `;
        })
        .join("");

    return `
      <article
        class="post-card${cardTierClass}"
        style="animation-delay:${index * 60}ms"
      >

        <div class="post-card__top">

          <span class="post-card__badge">
            AI ANALYSIS
          </span>

          ${
            relevance
              ? `
                <span
                  class="post-card__relevance post-card__relevance--${relevance.tier}"
                >
                  ${relevance.label} RELEVANCE
                </span>
              `
              : ""
          }

          <span class="post-card__time">
            ${escapeHtml(formatTimestamp(createdAt))}
          </span>

        </div>

        <h3 class="post-card__title">
          ${escapeHtml(title)}
        </h3>

        ${
          bodyText
            ? `
              <p class="post-card__text">
                ${escapeHtml(bodyText)}
              </p>
            `
            : ""
        }

        <div class="post-card__rationale">

          <span class="post-card__rationale-label">
            WHY CORTEX SELECTED THIS
          </span>

          <p class="post-card__rationale-text">
            ${escapeHtml(rationale)}
          </p>

        </div>

        <div class="post-card__footer">

          <div class="post-card__sources">

            ${
              sourceLinks ||
              `
                <span class="post-card__time">
                  No source listed
                </span>
              `
            }

          </div>

        </div>

      </article>
    `;
  }

  function renderPosts(posts) {
    if (!posts.length) {
      renderEmptyState();
      return;
    }

    const sorted =
      [...posts].sort((a, b) => {
        const da =
          new Date(
            a.createdAt ??
            a.created_at ??
            0
          ).getTime();

        const db =
          new Date(
            b.createdAt ??
            b.created_at ??
            0
          ).getTime();

        return db - da;
      });

    el.feedContent.innerHTML = `
      <div class="post-list">
        ${sorted
          .map((post, i) =>
            renderPostCard(post, i)
          )
          .join("")}
      </div>
    `;

    if (el.feedCount) {
      el.feedCount.textContent =
        `${posts.length} post${
          posts.length === 1 ? "" : "s"
        }`;
    }
  }

  // ------------------------------------------------------------------
  // Analytics
  // ------------------------------------------------------------------

  function updateAnalyticsFromPosts(posts) {
    const publishedCount =
      posts.length;

    animateCounter(
      el.metricPublished,
      publishedCount
    );

    animateCounter(
      el.analyticsPublished,
      publishedCount
    );

    /*
     * IMPORTANT:
     * Feed API only gives published posts.
     * We should NOT invent discovered/evaluated numbers.
     */
    if (el.metricDiscovered) {
      el.metricDiscovered.textContent = "—";
    }

    if (el.metricEvaluated) {
      el.metricEvaluated.textContent = "—";
    }

    if (el.analyticsDiscovered) {
      el.analyticsDiscovered.textContent = "—";
    }

    // Calculate average score only if backend actually sends it.
    const scores =
      posts
        .map(
          (p) =>
            Number(
              p.relevanceScore ??
              p.relevance_score ??
              p.score
            )
        )
        .filter(
          (n) => !Number.isNaN(n)
        );

    if (
      scores.length &&
      el.analyticsAvgScore
    ) {
      const avg =
        scores.reduce(
          (a, b) => a + b,
          0
        ) / scores.length;

      const normalized =
        avg > 1
          ? avg
          : avg * 100;

      el.analyticsAvgScore.textContent =
        `${Math.round(normalized)}%`;
    } else if (el.analyticsAvgScore) {
      el.analyticsAvgScore.textContent =
        "—";
    }

    // Latest published post.
    if (
      posts.length &&
      el.analyticsLast
    ) {
      const latest =
        posts
          .map(
            (p) =>
              new Date(
                p.createdAt ??
                p.created_at ??
                0
              ).getTime()
          )
          .filter(
            (t) => !Number.isNaN(t)
          )
          .sort(
            (a, b) => b - a
          )[0];

      el.analyticsLast.textContent =
        latest
          ? formatTimestamp(
              new Date(latest).toISOString()
            )
          : "—";
    } else if (el.analyticsLast) {
      el.analyticsLast.textContent =
        "—";
    }
  }

  // ------------------------------------------------------------------
  // API status
  // ------------------------------------------------------------------

  function setDot(
    dotEl,
    valEl,
    online,
    onlineLabel,
    offlineLabel
  ) {
    if (!dotEl || !valEl) {
      return;
    }

    dotEl.classList.remove(
      "dot--online",
      "dot--offline",
      "dot--pulse"
    );

    valEl.classList.remove(
      "is-online",
      "is-offline"
    );

    if (online) {
      dotEl.classList.add(
        "dot--online",
        "dot--pulse"
      );

      valEl.classList.add(
        "is-online"
      );

      valEl.textContent =
        onlineLabel;
    } else {
      dotEl.classList.add(
        "dot--offline"
      );

      valEl.classList.add(
        "is-offline"
      );

      valEl.textContent =
        offlineLabel;
    }
  }

  function setApiStatus(online) {
    setDot(
      el.statusApi,
      el.statusApiVal,
      online,
      "ONLINE",
      "OFFLINE"
    );

    setDot(
      el.statusDiscovery,
      el.statusDiscoveryVal,
      online,
      "ACTIVE",
      "OFFLINE"
    );

    setDot(
      el.statusPublisher,
      el.statusPublisherVal,
      online,
      "ACTIVE",
      "OFFLINE"
    );

    setDot(
      el.statusAgent,
      el.statusAgentVal,
      online,
      "ACTIVE",
      "OFFLINE"
    );

    if (el.navStatusText) {
      el.navStatusText.textContent =
        online
          ? "SYSTEM ONLINE"
          : "SYSTEM OFFLINE";
    }

    if (el.navStatusDot) {
      el.navStatusDot.classList.toggle(
        "dot--online",
        online
      );

      el.navStatusDot.classList.toggle(
        "dot--offline",
        !online
      );
    }
  }

  // ------------------------------------------------------------------
  // Fetch feed
  // ------------------------------------------------------------------

  async function loadFeed({
    showSkeleton = true
  } = {}) {

    if (showSkeleton) {
      renderSkeleton();
    }

    try {
      const res =
        await fetch(
          FEED_URL,
          {
            headers: {
              Accept:
                "application/json"
            }
          }
        );

      if (!res.ok) {
        throw new Error(
          `API responded with status ${res.status}`
        );
      }

      const data =
        await res.json();

      const posts =
        Array.isArray(data.posts)
          ? data.posts
          : [];

      renderPosts(posts);

      updateAnalyticsFromPosts(
        posts
      );

      setApiStatus(true);

    } catch (err) {

      console.error(
        "Failed to load feed:",
        err
      );

      renderErrorState(
        "Couldn't reach the Cortex API. " +
        "Make sure the Flask backend is running."
      );

      setApiStatus(false);
    }
  }

  // ------------------------------------------------------------------
  // Health check
  // ------------------------------------------------------------------

  async function checkHealth() {

    try {

      const res =
        await fetch(
          HEALTH_URL,
          {
            method: "GET",
            headers: {
              Accept:
                "application/json"
            }
          }
        );

      if (!res.ok) {
        throw new Error(
          `Health endpoint returned ${res.status}`
        );
      }

      const data =
        await res.json();

      setApiStatus(true);

      // If backend provides real scheduler status,
      // use it.
      if (
        typeof data.schedulerRunning ===
        "boolean"
      ) {

        setDot(
          el.statusPublisher,
          el.statusPublisherVal,
          data.schedulerRunning,
          "ACTIVE",
          "STOPPED"
        );
      }

    } catch (err) {

      console.warn(
        "Health check failed:",
        err
      );

      setApiStatus(false);
    }
  }

  // ------------------------------------------------------------------
  // Pipeline animation
  // ------------------------------------------------------------------

  function startPipelineAnimation() {

    if (!el.pipelineSteps.length) {
      return;
    }

    let i = 0;

    setInterval(() => {

      el.pipelineSteps.forEach(
        (step) =>
          step.classList.remove(
            "is-active"
          )
      );

      el.pipelineSteps[i].classList.add(
        "is-active"
      );

      i =
        (i + 1) %
        el.pipelineSteps.length;

    }, PIPELINE_CYCLE_MS);
  }

  // ------------------------------------------------------------------
  // Refresh
  // ------------------------------------------------------------------

  function handleRefreshClick() {

    if (!el.refreshBtn) {
      return;
    }

    el.refreshBtn.classList.add(
      "is-spinning"
    );

    Promise.all([
      loadFeed({
        showSkeleton: false
      }),
      checkHealth()
    ]).finally(() => {

      setTimeout(() => {

        el.refreshBtn.classList.remove(
          "is-spinning"
        );

      }, 400);

    });
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  function init() {

    if (el.refreshBtn) {
      el.refreshBtn.addEventListener(
        "click",
        handleRefreshClick
      );
    }

    loadFeed();
    checkHealth();
    startPipelineAnimation();

    setInterval(
      () =>
        loadFeed({
          showSkeleton: false
        }),
      AUTO_REFRESH_MS
    );

    setInterval(
      checkHealth,
      AUTO_REFRESH_MS
    );
  }

  document.addEventListener(
    "DOMContentLoaded",
    init
  );

})();