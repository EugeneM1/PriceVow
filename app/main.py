"""PriceVow web app - Phase 1 photo MVP.

Run it with:  uvicorn app.main:app --reload
Then open:    http://127.0.0.1:8000

One form in, one quote out. Photos are optional in v0: without an
ANTHROPIC_API_KEY the quote prices off the form answers alone (and the
gate counts the missing photos as a visibility gap, so it won't bind).
"""

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from . import gate, pricing, scope

app = FastAPI(title="PriceVow")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PriceVow</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 560px; margin: 40px auto; padding: 0 16px; }}
  h1 {{ font-size: 1.6rem; }} label {{ display: block; margin-top: 14px; font-weight: 600; }}
  input, select {{ width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }}
  button {{ margin-top: 20px; padding: 10px 22px; font-size: 1rem; cursor: pointer; }}
  .quote {{ border: 2px solid #2563eb; border-radius: 10px; padding: 18px; margin-top: 24px; }}
  .ceiling {{ font-size: 2rem; font-weight: 700; }}
  .muted {{ color: #666; font-size: 0.9rem; }}
  ul {{ margin: 8px 0; }}
</style></head><body>
<h1>PriceVow</h1>
<p class="muted">Guaranteed max price for your fence repair - from photos, no site visit.</p>
{body}
</body></html>"""

FORM = """
<form action="/quote" method="post" enctype="multipart/form-data">
  <label>How many feet of fence are affected?
    <input type="number" name="linear_feet" min="1" max="500" step="1" required></label>
  <label>Material
    <select name="material">
      <option value="cedar">Cedar / wood</option>
      <option value="vinyl">Vinyl</option>
      <option value="chain-link">Chain-link</option>
      <option value="wrought-iron">Wrought iron</option>
    </select></label>
  <label>How bad is the damage? (1 = cosmetic, 5 = leaning/rotten posts)
    <input type="number" name="damage_severity" min="1" max="5" step="1" required></label>
  <label>Gates in the damaged section
    <input type="number" name="gate_count" min="0" max="10" step="1" value="0"></label>
  <label>ZIP code
    <input type="text" name="zip_code" pattern="[0-9]{5}" required></label>
  <label>Photos or documents (optional in v0) - images, PDF reports, saved HTML pages
    <input type="file" name="photos" accept="image/*,.pdf,.html,.htm" multiple></label>
  <button type="submit">Get my guaranteed price</button>
</form>"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE.format(body=FORM)


@app.post("/quote", response_class=HTMLResponse)
async def quote(
    linear_feet: float = Form(...),
    material: str = Form(...),
    damage_severity: int = Form(...),
    gate_count: int = Form(0),
    zip_code: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
) -> str:
    # 1. Perception: build the scope.
    form_scope = scope.scope_from_form(
        linear_feet, material, damage_severity, gate_count, zip_code
    )
    attachments = [
        scope.Attachment(filename=p.filename, data=await p.read())
        for p in photos
        if p.filename
    ]
    kinds = {a.kind for a in attachments}
    if "image" in kinds:
        form_scope.visibility_gaps = []  # photos replace the "no photos" gap
    elif kinds & {"pdf", "html"}:
        # Documents help, but they aren't eyes on the fence itself.
        form_scope.visibility_gaps = ["documents only - no photos of the fence"]
    vision_scope = scope.scope_from_attachments(attachments, form_scope)
    job_scope = scope.best_scope(form_scope, vision_scope)

    # 2. Judgment: can we afford to promise a ceiling?
    decision = gate.assess(job_scope)

    # 3. Pricing: deterministic code over the rate card.
    result = pricing.price(job_scope)

    if decision.binds:
        headline = f"""<div class="quote">
          <div>Your guaranteed maximum price</div>
          <div class="ceiling">${result.ceiling(decision.risk_tier):,.0f}</div>
          <div class="muted">Expected around ${result.expected_cost:,.0f}.
          You will never pay above the ceiling. Valid 7 days.</div></div>"""
    else:
        headline = f"""<div class="quote">
          <div>Estimated range (not yet guaranteed)</div>
          <div class="ceiling">${result.low:,.0f} - ${result.high:,.0f}</div>
          <div class="muted">We need a short guided video to lock in a
          guaranteed price for this one.</div></div>"""

    details = "".join(f"<li>{r}</li>" for r in decision.reasons)
    body = f"""{headline}
      <p class="muted">Confidence {decision.bindable_prob:.0%} &middot;
      risk tier: {decision.risk_tier} &middot; scope source: {job_scope.source}
      &middot; rate card {result.rate_card_version}</p>
      <ul class="muted">{details}</ul>
      <p><a href="/">&larr; New quote</a></p>"""
    return PAGE.format(body=body)
