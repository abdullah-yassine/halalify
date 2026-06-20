"""
Core halal classification engine.

Takes a product's raw ingredient text (and optionally its brand) and returns
a verdict of HALAL, HARAM, or DOUBTFUL with full reasoning.

This module has no dependency on views, serializers, or request objects —
it is plain, testable Python that the API layer calls.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from products.models import Certification, Ingredient


class Verdict(str, Enum):
    HALAL = "halal"
    HARAM = "haram"
    DOUBTFUL = "doubtful"


@dataclass
class TriggeredIngredient:
    name: str
    reason: str
    matched: bool = True  # False = ingredient not found in our DB ("not yet classified")


@dataclass
class ClassificationResult:
    verdict: Verdict
    # HARAM: single-element list (the first haram ingredient found)
    # DOUBTFUL: all triggering ingredients, including unrecognised ones
    # HALAL: empty
    triggers: list[TriggeredIngredient] = field(default_factory=list)
    certifying_body: Optional[str] = None  # set when a certification overrides Doubtful → Halal


# ---------------------------------------------------------------------------
# Ingredient text parser
# ---------------------------------------------------------------------------

_STRIP_LABEL = re.compile(r"^ingredients\s*:\s*", re.IGNORECASE)
_WS = re.compile(r"\s+")

_UNCLASSIFIED_REASON = (
    "Ingredient not yet classified in our database — "
    "verify independently with the manufacturer or a certifying body."
)


def _normalize(text: str) -> str:
    return _WS.sub(" ", text).lower().strip(" .,;")


def parse_ingredients(text: str) -> list[str]:
    """
    Split a raw Open Food Facts ingredient string into individual tokens.

    Parenthetical sub-ingredients are extracted as separate tokens alongside
    their parent so the classifier can check each component individually.

    Examples:
      "Water, Sugar, Salt"
        → ["Water", "Sugar", "Salt"]
      "Enriched Flour (Wheat Flour, Niacin, Iron), Sugar"
        → ["Enriched Flour", "Wheat Flour", "Niacin", "Iron", "Sugar"]
    """
    text = _STRIP_LABEL.sub("", text.strip()).rstrip(".")

    tokens: list[str] = []
    depth = 0
    current: list[str] = []
    sub: list[str] = []

    for ch in text:
        if ch == "(":
            depth += 1
            if depth == 1:
                # Flush the parent name collected so far
                parent = "".join(current).strip()
                if parent:
                    tokens.append(parent)
                current = []
                sub = []
            else:
                sub.append(ch)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                for part in "".join(sub).split(","):
                    part = part.strip()
                    if part:
                        tokens.append(part)
            else:
                sub.append(ch)
        elif ch == "," and depth == 0:
            tok = "".join(current).strip()
            if tok:
                tokens.append(tok)
            current = []
        elif depth == 0:
            current.append(ch)
        else:
            sub.append(ch)

    tail = "".join(current).strip()
    if tail:
        tokens.append(tail)

    return [t for t in tokens if t]


# ---------------------------------------------------------------------------
# Token → Ingredient matching
# ---------------------------------------------------------------------------

_SEVERITY = {
    Ingredient.Category.HARAM: 3,
    Ingredient.Category.DOUBTFUL: 2,
    Ingredient.Category.HALAL: 1,
}


def _best_match(
    token: str, all_ingredients: list[Ingredient]
) -> Optional[Ingredient]:
    """
    Return the best-matching Ingredient for this token, or None.

    Matching strategy (case-insensitive, one direction only):
      An ingredient matches when any of its terms (name, e_number, aliases)
      appears as a substring INSIDE the token — never the reverse.

      Directional-only prevents "gelatin" (token) from matching "Pork Gelatin"
      (ingredient) just because "gelatin" is a suffix of the longer name.
      "pork gelatin" (token) still correctly matches "Pork" AND "Pork Gelatin"
      because both terms appear inside "pork gelatin".

    When multiple ingredients match, we rank by:
      1. Severity (haram > doubtful > halal)
      2. Specificity (length of the longest matching term — longer = more precise)
    """
    norm_tok = _normalize(token)
    if not norm_tok:
        return None

    best: Optional[tuple[int, int, Ingredient]] = None  # (severity, specificity, ingredient)

    for ing in all_ingredients:
        terms = [_normalize(ing.name)]
        if ing.e_number:
            terms.append(_normalize(ing.e_number))
        terms.extend(_normalize(a) for a in (ing.aliases or []))

        longest_match = max(
            (len(term) for term in terms if term and term in norm_tok),
            default=0,
        )
        if longest_match == 0:
            continue

        severity = _SEVERITY.get(ing.category, 0)
        score = (severity, longest_match)
        if best is None or score > best[:2]:
            best = (severity, longest_match, ing)

    return best[2] if best is not None else None


# ---------------------------------------------------------------------------
# Main classification function
# ---------------------------------------------------------------------------


def classify(ingredients_text: str, brand: str = "") -> ClassificationResult:
    """
    Classify a product as HALAL, HARAM, or DOUBTFUL.

    Algorithm (CLAUDE.md §3):
      1. Parse raw ingredient text into tokens.
      2. Match each token against the Ingredient table (name + aliases).
      3. First HARAM match → return HARAM immediately (short-circuit).
      4. Collect DOUBTFUL matches + unrecognised tokens as candidates.
         Unrecognised = safe failure mode is DOUBTFUL, never HALAL.
      5. If brand has an active Certification → HALAL (overrides candidates).
      6. No candidates → HALAL.
      7. Candidates present, no cert → DOUBTFUL.
    """
    tokens = parse_ingredients(ingredients_text)

    # No tokens means no ingredient data at all (empty string, whitespace, or
    # a label-only string like "INGREDIENTS:"). Per CLAUDE.md §3 the safe
    # failure mode is DOUBTFUL — never assume Halal due to missing data.
    if not tokens:
        return ClassificationResult(
            verdict=Verdict.DOUBTFUL,
            triggers=[
                TriggeredIngredient(
                    name="No ingredient data",
                    reason=(
                        "Ingredient information is not available for this product. "
                        "Please verify independently with the manufacturer or a certifying body."
                    ),
                    matched=False,
                )
            ],
        )

    # Load all ingredients once — table is small enough to fit in memory.
    all_ingredients = list(Ingredient.objects.all())

    doubtful_candidates: list[TriggeredIngredient] = []
    seen_names: set[str] = set()  # deduplicate repeated ingredients

    for token in tokens:
        match = _best_match(token, all_ingredients)

        if match is None:
            # Unknown ingredient — safe failure mode is DOUBTFUL.
            if token not in seen_names:
                seen_names.add(token)
                doubtful_candidates.append(
                    TriggeredIngredient(
                        name=token,
                        reason=_UNCLASSIFIED_REASON,
                        matched=False,
                    )
                )
        elif match.category == Ingredient.Category.HARAM:
            return ClassificationResult(
                verdict=Verdict.HARAM,
                triggers=[TriggeredIngredient(name=match.name, reason=match.reason)],
            )
        elif match.category == Ingredient.Category.DOUBTFUL:
            if match.name not in seen_names:
                seen_names.add(match.name)
                doubtful_candidates.append(
                    TriggeredIngredient(name=match.name, reason=match.reason)
                )
        # HALAL match: no action needed.

    # Check brand certification (only meaningful if there are candidates to override).
    if brand:
        cert = Certification.objects.filter(
            brand__iexact=brand, certified=True
        ).first()
        if cert:
            return ClassificationResult(
                verdict=Verdict.HALAL,
                certifying_body=cert.get_certifying_body_display(),
            )

    if not doubtful_candidates:
        return ClassificationResult(verdict=Verdict.HALAL)

    return ClassificationResult(verdict=Verdict.DOUBTFUL, triggers=doubtful_candidates)
