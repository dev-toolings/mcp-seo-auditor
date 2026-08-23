"""AI-crawler / robots.txt / llms.txt auditor for GEO.

Classifies AI user-agents into three intents and flags the costly mistake of blocking
the *retrieval* bots that feed AI citations while wanting to block only *training* bots.

Intent classes:
    training — crawl content to train foundation models (blocking is a valid choice)
    search  — fetch pages to ground / cite answers in real time (blocking kills AI
              visibility — these are the ones you almost always want to ALLOW)
    user    — fetch a page because a user pasted/asked about that URL (blocking hurts UX)
"""

import logging
import re

logger = logging.getLogger(__name__)

# Known AI user-agents and their retrieval intent (2026).
AI_USER_AGENTS = {
    # ── OpenAI ──
    "GPTBot": "training",
    "OAI-SearchBot": "search",
    "ChatGPT-User": "user",
    # ── Anthropic ──
    "ClaudeBot": "training",
    "anthropic-ai": "training",
    "Claude-SearchBot": "search",
    "Claude-User": "user",
    # ── Perplexity ──
    "PerplexityBot": "search",
    "Perplexity-User": "user",
    # ── Google ──
    "Google-Extended": "training",  # gates Gemini/Vertex training & AIO grounding
    "GoogleOther": "search",
    # ── Others ──
    "Applebot-Extended": "training",
    "Bytespider": "training",
    "CCBot": "training",
    "Amazonbot": "search",
    "Meta-ExternalAgent": "training",
    "cohere-ai": "training",
}

# Bots whose blocking directly suppresses AI citations / answer-engine visibility.
CITATION_CRITICAL = {
    "OAI-SearchBot",
    "Claude-SearchBot",
    "PerplexityBot",
    "ChatGPT-User",
    "Perplexity-User",
    "Claude-User",
    "GoogleOther",
}

RECOMMENDED_ROBOTS_2026 = """\
# Recommended 2026 robots.txt for AI search visibility.
# Allow retrieval/citation bots; block training crawlers only if that is your policy.

# --- AI training crawlers (block only if you do not want model training on your content) ---
User-agent: GPTBot
User-agent: ClaudeBot
User-agent: anthropic-ai
User-agent: Google-Extended
User-agent: CCBot
User-agent: Bytespider
User-agent: Applebot-Extended
User-agent: Meta-ExternalAgent
Disallow: /

# --- AI retrieval / citation bots (KEEP ALLOWED for AI visibility) ---
User-agent: OAI-SearchBot
User-agent: Claude-SearchBot
User-agent: PerplexityBot
User-agent: ChatGPT-User
User-agent: Perplexity-User
User-agent: Claude-User
User-agent: GoogleOther
Allow: /

Sitemap: {sitemap_url}
"""


class LLMsTxtChecker:
    """Audit robots.txt / llms.txt for AI-crawler handling."""

    def analyze(
        self,
        robots_txt: str,
        llms_txt: str | None = None,
        sitemap_url: str = "https://example.com/sitemap.xml",
    ) -> dict:
        """Analyze AI-crawler directives.

        Args:
            robots_txt: Raw robots.txt content.
            llms_txt: Raw llms.txt content (optional).
            sitemap_url: Sitemap URL to embed in the generated template.

        Returns:
            dict with classification, blocked citation bots, llms.txt status,
            a recommended robots.txt, score (0-100) and issues.
        """
        blocked = self._parse_blocked_agents(robots_txt or "")

        classification: dict[str, list[dict[str, object]]] = {
            "training": [],
            "search": [],
            "user": [],
            "unknown": [],
        }
        for agent, intent in AI_USER_AGENTS.items():
            entry = {"agent": agent, "blocked": agent in blocked or "*" in blocked}
            classification[intent].append(entry)

        blocked_citation = sorted(a for a in CITATION_CRITICAL if a in blocked or "*" in blocked)

        issues: list[str] = []
        score = 100
        if "*" in blocked:
            issues.append(
                "robots.txt blocks all user-agents (User-agent: * Disallow: /). "
                "AI retrieval bots cannot cite this site."
            )
            score = 0
        for agent in blocked_citation:
            issues.append(
                f"{agent} ({AI_USER_AGENTS[agent]}) is blocked — this suppresses AI citations. "
                "Allow it to stay visible in answer engines."
            )
        if blocked_citation and score > 0:
            score = max(20, 100 - 20 * len(blocked_citation))

        llms_present = bool(llms_txt and llms_txt.strip())
        llms_note = (
            "llms.txt present."
            if llms_present
            else "No llms.txt found. Low-yield today (limited engine support) but cheap to add "
            "as a curated index of your most citable pages."
        )

        return {
            "score": max(0, min(100, score)),
            "classification": classification,
            "blocked_agents": sorted(blocked),
            "blocked_citation_bots": blocked_citation,
            "llms_txt_present": llms_present,
            "llms_txt_note": llms_note,
            "recommended_robots_txt": RECOMMENDED_ROBOTS_2026.format(sitemap_url=sitemap_url),
            "issues": issues,
        }

    def _parse_blocked_agents(self, robots_txt: str) -> set[str]:
        """Return the set of user-agents that have a `Disallow: /` rule.

        A simplified parser: groups consecutive ``User-agent`` lines and marks every
        agent in the group as blocked if the group contains a root ``Disallow: /``
        without an overriding ``Allow: /``.
        """
        blocked: set[str] = set()
        current_agents: list[str] = []
        group_disallow_root = False
        group_allow_root = False

        def _flush():
            if current_agents and group_disallow_root and not group_allow_root:
                blocked.update(current_agents)

        for raw in robots_txt.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "user-agent":
                # New group starts after a directive line was seen
                if group_disallow_root or group_allow_root:
                    _flush()
                    current_agents = []
                    group_disallow_root = False
                    group_allow_root = False
                current_agents.append(value)
            elif key == "disallow" and value == "/":
                group_disallow_root = True
            elif key == "allow" and value == "/":
                group_allow_root = True
            elif key in ("disallow", "allow"):
                continue
        _flush()
        # Normalize wildcard
        if "*" in blocked:
            blocked.add("*")
        return {re.sub(r"\s+", "", a) for a in blocked if a}
