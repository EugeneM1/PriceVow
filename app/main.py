"""PriceVow web app - Phase 1 photo MVP.

Run it with:  uvicorn app.main:app --reload
Then open:    http://127.0.0.1:8000

One form in, one quote out. Photos are optional in v0: without an
ANTHROPIC_API_KEY the quote prices off the form answers alone (and the
gate counts the missing photos as a visibility gap, so it won't bind).
"""

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from . import calibration, contractors, judgment, pricing, scope, video

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
  <label>Photos, a short walkthrough video, or documents (images, video, PDF, HTML)
    <input type="file" name="photos" accept="image/*,video/*,.pdf,.html,.htm" multiple></label>
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

    # Videos become image frames before perception sees them.
    frame_failures = 0
    expanded: list[scope.Attachment] = []
    for a in attachments:
        if a.kind != "video":
            expanded.append(a)
            continue
        frames = video.extract_frames(a.data)
        if frames:
            expanded.extend(
                scope.Attachment(filename=f"{a.filename}.frame{i:02d}.jpg", data=f)
                for i, f in enumerate(frames, 1)
            )
        else:
            frame_failures += 1
    attachments = expanded

    kinds = {a.kind for a in attachments}
    if "image" in kinds:
        form_scope.visibility_gaps = []  # photos/frames replace the "no photos" gap
    elif kinds & {"pdf", "html"}:
        # Documents help, but they aren't eyes on the fence itself.
        form_scope.visibility_gaps = ["documents only - no photos of the fence"]
    if frame_failures:
        form_scope.visibility_gaps.append("uploaded video could not be processed")
    vision_scope = scope.scope_from_attachments(attachments, form_scope)
    job_scope = scope.best_scope(form_scope, vision_scope)

    # 2. Judgment: can we afford to promise a ceiling?
    # (rules today; PRICEVOW_JUDGE=jev swaps in Jev at Phase 2)
    decision = judgment.get_judge().assess(job_scope)

    # 3. Pricing: deterministic code over the rate card.
    result = pricing.price(job_scope)

    # 4. Calibration: every quote goes on the record.
    job_id = calibration.record_quote(job_scope, decision, result)

    if decision.binds:
        headline = f"""<div class="quote">
          <div>Your guaranteed maximum price</div>
          <div class="ceiling">${result.ceiling(decision.risk_tier):,.0f}</div>
          <div class="muted">Expected around ${result.expected_cost:,.0f}.
          You will never pay above the ceiling. Valid 7 days.</div>
          <form action="/jobs/{job_id}/book" method="post" style="margin-top:12px">
            <button>Book at this price</button></form></div>"""
    else:
        headline = f"""<div class="quote">
          <div>Estimated range (not yet guaranteed)</div>
          <div class="ceiling">${result.low:,.0f} - ${result.high:,.0f}</div>
          <div class="muted">We need a short guided video to lock in a
          guaranteed price for this one.</div></div>"""

    details = "".join(f"<li>{r}</li>" for r in decision.reasons)
    body = f"""{headline}
      <p class="muted">Quote {job_id} &middot; confidence {decision.bindable_prob:.0%} &middot;
      risk tier: {decision.risk_tier} &middot; scope source: {job_scope.source}
      &middot; rate card {result.rate_card_version}</p>
      <ul class="muted">{details}</ul>
      <p><a href="/">&larr; New quote</a> &middot; <a href="/jobs">All quotes</a></p>"""
    return PAGE.format(body=body)


# ---------------------------------------------------------------------------
# Admin: the calibration loop's front door.
# Record what each job ACTUALLY cost, then watch the accuracy report.
# ---------------------------------------------------------------------------


@app.get("/jobs", response_class=HTMLResponse)
def jobs() -> str:
    rows = []
    for j in calibration.list_jobs():
        promised = f"${j['ceiling']:,.0f}" if j["bound"] else "range only"
        if j["bound"] and j.get("booked"):
            promised += " &middot; booked"
        invoiced = (
            f"${j['invoiced_cost']:,.0f}"
            if j["invoiced_cost"] is not None
            else f"""<form action="/jobs/{j['id']}/invoice" method="post" style="margin:0">
                 <input name="invoiced_cost" type="number" step="1" min="1"
                        placeholder="actual $" style="width:90px">
                 <button>save</button></form>"""
        )
        rows.append(
            f"<tr><td>{j['id']}</td><td>{j['created_at'][:10]}</td>"
            f"<td>{j['zip_code']}</td><td>${j['expected_cost']:,.0f}</td>"
            f"<td>{promised}</td><td>{invoiced}</td></tr>"
        )
    table = (
        "<table border=1 cellpadding=6 cellspacing=0>"
        "<tr><th>Quote</th><th>Date</th><th>ZIP</th><th>Expected</th>"
        "<th>Promised</th><th>Invoiced (enter when job is done)</th></tr>"
        + "".join(rows)
        + "</table>"
    ) if rows else "<p>No quotes yet - issue one from the <a href='/'>home page</a>.</p>"
    body = f"""<h2>Quotes</h2>{table}
      <p><a href="/calibration">Calibration report</a> &middot; <a href="/">New quote</a></p>"""
    return PAGE.format(body=body)


@app.post("/jobs/{job_id}/book")
def book(job_id: str) -> HTMLResponse:
    calibration.record_booking(job_id)
    try:
        contractor_id = contractors.offer_job(job_id)
        line = f"Booked. Job offered to contractor {contractor_id} - they have 24h to accept."
    except LookupError:
        line = ("Booked, but no registered contractor covers this ZIP yet - "
                "add one at /contractors, then re-offer from the offers page.")
    body = f"""<div class="quote"><b>{line}</b></div>
      <p><a href="/jobs">All quotes</a> &middot; <a href="/contractors">Contractors</a></p>"""
    return HTMLResponse(PAGE.format(body=body))


@app.post("/jobs/{job_id}/invoice")
def save_invoice(job_id: str, invoiced_cost: float = Form(...)) -> RedirectResponse:
    calibration.record_invoice(job_id, invoiced_cost)
    return RedirectResponse(url="/jobs", status_code=303)


@app.get("/contractors", response_class=HTMLResponse)
def contractors_page() -> str:
    roster = "".join(
        f"<tr><td>{c['id']}</td><td>{c['name']}</td><td>{c['email'] or ''}</td>"
        f"<td>{c['zips']}</td><td>{'yes' if c['active'] else 'no'}</td></tr>"
        for c in contractors.list_contractors()
    )
    roster_table = (
        "<table border=1 cellpadding=6 cellspacing=0>"
        "<tr><th>Id</th><th>Name</th><th>Email</th><th>ZIPs</th><th>Active</th></tr>"
        + roster + "</table>"
    ) if roster else "<p>No contractors yet - sign your Phase 0 partners up here.</p>"

    offers = "".join(
        f"""<tr><td>{o['job_id']}</td><td>{o['contractor_name']}</td>
            <td>{o['zip_code']}</td><td>${o['ceiling']:,.0f}</td>
            <td><form action="/offers/{o['id']}/decide" method="post" style="margin:0">
              <button name="accept" value="1">accept</button>
              <button name="accept" value="0">decline</button>
              <input name="reason" placeholder="decline reason" style="width:140px">
            </form></td></tr>"""
        for o in contractors.pending_offers()
    )
    offers_table = (
        "<h3>Pending offers</h3><table border=1 cellpadding=6 cellspacing=0>"
        "<tr><th>Job</th><th>Contractor</th><th>ZIP</th><th>Ceiling</th><th>Decision</th></tr>"
        + offers + "</table>"
    ) if offers else "<h3>Pending offers</h3><p>None.</p>"

    body = f"""<h2>Contractors</h2>{roster_table}
      <h3>Add a contractor</h3>
      <form action="/contractors" method="post">
        <label>Name <input name="name" required></label>
        <label>Email <input name="email" type="email"></label>
        <label>ZIPs served (comma-separated) <input name="zips" required
               placeholder="90024,90025,90064"></label>
        <button>Add</button>
      </form>
      {offers_table}
      <p><a href="/jobs">Quotes</a> &middot; <a href="/">New quote</a></p>"""
    return PAGE.format(body=body)


@app.post("/contractors")
def add_contractor(
    name: str = Form(...), email: str = Form(""), zips: str = Form(...)
) -> RedirectResponse:
    contractors.add_contractor(name, email, [z for z in zips.split(",") if z.strip()])
    return RedirectResponse(url="/contractors", status_code=303)


@app.post("/offers/{offer_id}/decide")
def decide_offer(
    offer_id: int, accept: str = Form(...), reason: str = Form("")
) -> RedirectResponse:
    contractors.decide_offer(offer_id, accept == "1", reason)
    return RedirectResponse(url="/contractors", status_code=303)


@app.get("/calibration", response_class=HTMLResponse)
def calibration_report() -> str:
    r = calibration.report()
    err = f"{r.median_abs_error_pct}%" if r.median_abs_error_pct is not None else "n/a"
    gate_line = (
        "<b style='color:green'>PASSES the Phase 0 gate (&le;15% on 5+ jobs)</b>"
        if r.passes_phase0_gate
        else "Does not pass the Phase 0 gate yet (&le;15% median error on 5+ invoiced jobs)"
    )
    body = f"""<h2>Calibration report</h2>
      <ul>
        <li>Quotes issued: {r.quotes_issued} (bound: {r.quotes_bound})</li>
        <li>Jobs with invoiced cost: {r.jobs_invoiced}</li>
        <li>Median absolute error: <b>{err}</b></li>
        <li>Ceiling overruns: {r.overruns} (guarantee paid out ${r.overrun_paid_total:,.2f})</li>
      </ul>
      <p>{gate_line}</p>
      {_tuning_section()}
      <p><a href="/jobs">Quotes</a> &middot; <a href="/">New quote</a></p>"""
    return PAGE.format(body=body)


def _tuning_section() -> str:
    t = calibration.suggest_tuning()
    if not t.samples_per_tier:
        return "<p class='muted'>Spread tuning: no invoiced jobs yet.</p>"
    lines = []
    for tier, current in t.current_spread_per_tier.items():
        n = t.samples_per_tier.get(tier, 0)
        if tier in t.suggested_spread_per_tier:
            s = t.suggested_spread_per_tier[tier]
            move = "tighten to" if s < current else "widen to"
            lines.append(
                f"<li>{tier}: current {current:.0%}, {n} samples - "
                f"<b>{move} {s:.0%}</b> (covers ~90% of realized costs)</li>"
            )
        else:
            lines.append(
                f"<li>{tier}: current {current:.0%}, {n} samples - "
                f"need {calibration.Tuning.MIN_SAMPLES}+ to recommend</li>"
            )
    return (
        "<h3>Spread tuning (recommendations only)</h3><ul>"
        + "".join(lines)
        + "</ul><p class='muted'>Apply by editing SPREAD_BY_TIER in app/pricing.py "
        "and bumping the rate card version.</p>"
    )
