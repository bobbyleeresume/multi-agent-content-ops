"""
guardrails.py

Output guardrails for free-text LLM content (CommsAgent narrative) before it
leaves the pipeline. Redacts PII (emails, phone numbers) and flags a small
blocklist. Deterministic, offline, dependency-free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
BLOCKLIST = {"confidential", "internal-only", "do not distribute"}


@dataclass
class GuardResult:
    text: str
    redactions: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.flags


def scrub(text: str) -> GuardResult:
    redactions = 0
    text, n = EMAIL_RE.subn("[redacted-email]", text)
    redactions += n
    text, n = PHONE_RE.subn("[redacted-phone]", text)
    redactions += n
    flags = [w for w in BLOCKLIST if w.lower() in text.lower()]
    return GuardResult(text=text, redactions=redactions, flags=flags)
