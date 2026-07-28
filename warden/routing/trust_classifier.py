"""
Trust classifier — determines how to route content based on its origin.

Trusted content → P-LLM path (direct, no guard needed)
Untrusted content → Q-LLM path (quarantined, guarded)
"""

from __future__ import annotations

from warden.config import TrustLevel, ContentSource


class TrustClassifier:
    """Classifies content trust level based on source and heuristics."""

    # Source → trust level mapping
    SOURCE_TRUST: dict[ContentSource, TrustLevel] = {
        ContentSource.USER_DIRECT: TrustLevel.TRUSTED,
        ContentSource.LOCAL_FILE: TrustLevel.TRUSTED,
        ContentSource.FETCHED_URL: TrustLevel.UNTRUSTED,
        ContentSource.TOOL_OUTPUT: TrustLevel.UNTRUSTED,
        ContentSource.CODE_DIFF: TrustLevel.UNTRUSTED,
        ContentSource.UNKNOWN: TrustLevel.AMBIGUOUS,
    }

    def classify(self, content: str, source: ContentSource) -> TrustLevel:
        """
        Determine trust level of content.

        Rules:
        - USER_DIRECT → Trusted
        - LOCAL_FILE → Trusted (user's own files)
        - FETCHED_URL → Untrusted
        - TOOL_OUTPUT → Untrusted (tool could return attacker data)
        - CODE_DIFF → Untrusted (AI-generated code needs review)
        - UNKNOWN → Ambiguous → treat as Untrusted
        """
        base_trust = self.SOURCE_TRUST.get(source, TrustLevel.AMBIGUOUS)

        # Ambiguous always treated as untrusted for safety
        if base_trust == TrustLevel.AMBIGUOUS:
            return TrustLevel.UNTRUSTED

        return base_trust
