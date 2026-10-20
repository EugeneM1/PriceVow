"""Scope = a structured, machine-readable description of the job.

This is the "perception layer" of PriceVow. In v0 the scope comes
straight from the homeowner's form answers. If an ANTHROPIC_API_KEY
is set and photos were uploaded, we also ask Claude vision to read
the photos and we prefer its measurements when they disagree a lot
with the homeowner's guess (people are bad at estimating feet).

Nothing in this file touches money. Pricing lives in pricing.py.
"""

from dataclasses import dataclass, field
import json
import os


# The only trade we handle in Phase 1. Paint comes in Phase 3.
MATERIALS = ["cedar", "vinyl", "chain-link", "wrought-iron"]


@dataclass
class Scope:
    """Everything the pricing engine needs to know about one fence job."""

    linear_feet: float
    material: str  # one of MATERIALS
    damage_severity: int  # 1 (cosmetic) .. 5 (structural / rot)
    gate_count: int = 0
    zip_code: str = ""
    # Things the photos did NOT show. Each gap lowers our confidence.
    # Examples: "post footings not visible", "only one side photographed".
    visibility_gaps: list[str] = field(default_factory=list)
    # Where the numbers came from: "form" or "vision".
    source: str = "form"


def scope_from_form(
    linear_feet: float,
    material: str,
    damage_severity: int,
    gate_count: int,
    zip_code: str,
) -> Scope:
    """Build a Scope from the homeowner's answers alone (no AI)."""
    material = material.lower().strip()
    if material not in MATERIALS:
        raise ValueError(f"material must be one of {MATERIALS}, got {material!r}")
    if not 1 <= damage_severity <= 5:
        raise ValueError("damage_severity must be 1-5")
    if linear_feet <= 0:
        raise ValueError("linear_feet must be positive")
    return Scope(
        linear_feet=linear_feet,
        material=material,
        damage_severity=damage_severity,
        gate_count=gate_count,
        zip_code=zip_code,
        # With no photos we are blind, and the gate treats that as a gap.
        visibility_gaps=["no photos provided"],
        source="form",
    )


# ---------------------------------------------------------------------------
# Claude vision (optional in v0)
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are the perception layer of a home-repair quoting system.
Look at the attached photos of a fence and the homeowner's answers, then
return ONLY a JSON object with these keys:

  linear_feet      number - your best estimate of affected fence length
  material         one of: cedar, vinyl, chain-link, wrought-iron
  damage_severity  integer 1-5 (1 cosmetic, 3 broken boards/panels,
                   5 leaning posts, rot at footings, structural)
  gate_count       integer - gates visible in the affected run
  visibility_gaps  array of short strings describing what you could NOT
                   see but would need for a confident quote (e.g.
                   "post footings not visible", "far end of run cut off")

Homeowner's answers (may be wrong - trust the photos for measurements):
{answers_json}
"""


def scope_from_photos(photo_bytes_list: list[bytes], form_scope: Scope) -> Scope | None:
    """Ask Claude vision to read the photos. Returns None when no API key
    is configured, so the app still works in pure form mode."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not photo_bytes_list:
        return None

    import base64

    import anthropic  # imported here so the app runs without the package too

    client = anthropic.Anthropic(api_key=api_key)
    answers = {
        "linear_feet": form_scope.linear_feet,
        "material": form_scope.material,
        "damage_severity": form_scope.damage_severity,
        "gate_count": form_scope.gate_count,
    }
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(b).decode(),
            },
        }
        for b in photo_bytes_list[:6]  # cap at 6 photos
    ]
    content.append(
        {"type": "text", "text": VISION_PROMPT.format(answers_json=json.dumps(answers))}
    )

    message = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=500,
        messages=[{"role": "user", "content": content}],
    )
    raw = message.content[0].text
    # The model sometimes wraps JSON in a code fence; strip it.
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    data = json.loads(raw)

    return Scope(
        linear_feet=float(data["linear_feet"]),
        material=str(data["material"]).lower(),
        damage_severity=int(data["damage_severity"]),
        gate_count=int(data.get("gate_count", form_scope.gate_count)),
        zip_code=form_scope.zip_code,
        visibility_gaps=[str(g) for g in data.get("visibility_gaps", [])],
        source="vision",
    )


def best_scope(form_scope: Scope, vision_scope: Scope | None) -> Scope:
    """Pick the scope to price from. Vision wins on measurements when it
    disagrees with the homeowner by 20% or more (design rule from the
    data model: 'vision value wins on conflict >= 20%')."""
    if vision_scope is None:
        return form_scope
    disagreement = abs(vision_scope.linear_feet - form_scope.linear_feet) / max(
        form_scope.linear_feet, 1.0
    )
    if disagreement >= 0.20:
        return vision_scope
    # Close enough: keep the homeowner's number but adopt the photo-derived
    # severity and gaps, which humans judge worse than length.
    form_scope.damage_severity = vision_scope.damage_severity
    form_scope.visibility_gaps = vision_scope.visibility_gaps
    form_scope.source = "form+vision"
    return form_scope
