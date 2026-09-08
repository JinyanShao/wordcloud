"""Boundaries for using DBnary Chinese translation candidates in learner content.

This module deliberately makes no linguistic or semantic judgment.  It keeps
the ordering of the future pipeline explicit:

    learner-priority sense selection -> candidate lookup -> semantic review

Candidate availability (including a structural DBnary sense-number mapping)
must never choose or promote the learner-priority sense.  CEFR is a
lexeme-level discovery signal only, not evidence that any particular sense is
beginner-priority.
"""
from __future__ import annotations

from typing import Mapping


STRUCTURALLY_SENSE_MAPPED = "sense_mapped_candidate"
SEMANTIC_REVIEW_REQUIRED = "requires_semantic_review"


def candidate_context_for_selected_sense(
    selected_sense_id: str,
    candidate: Mapping[str, object],
) -> dict[str, object]:
    """Return structural context without approving a Chinese learner gloss.

    ``sense_mapped_candidate`` means only that a DBnary gloss sense number
    structurally resolved to a current SQLite sense.  Even a matching sense
    remains subject to editorial/semantic review; a mismatch is unavailable
    for source reuse for this selected sense.
    """
    mapped_sense_id = candidate.get("mapped_sense_id")
    structural_match = (
        candidate.get("candidate_class") == STRUCTURALLY_SENSE_MAPPED
        and mapped_sense_id == selected_sense_id
    )
    return {
        "candidate_class": candidate.get("candidate_class"),
        "structural_match_for_selected_sense": structural_match,
        "semantic_status": SEMANTIC_REVIEW_REQUIRED,
        "automatic_learner_gloss_approval": False,
    }
