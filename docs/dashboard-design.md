# Design Prompt — Purchase Requisition Agent Dashboard

Use this as a Cursor prompt file (`docs/dashboard-design.md`) for the SAP BTP AI Agent
for Purchase Requisition Triage frontend. Stack: Next.js, Tailwind, shadcn/ui primitives
where useful, Recharts for analytics.

---

## 1. Ground it in the subject

This is **not** a generic SaaS admin panel. It is a **triage cockpit** for a procurement
officer who is reviewing AI-screened purchase requisitions before they hit SAP. The
single job of this page: let one person look at a queue of requisitions, see which ones
the agent flags as risky (bad vendor, price anomaly, policy violation), and clear or
escalate them fast — without re-reading a wall of ERP fields.

There are two distinct personas sharing this product, and they need two distinct views:

- **Unit requester** — someone in HR, IT, Facilities, Manufacturing, etc. who originates
  a PR against their own cost center and needs to get it approved into a PO. They care
  about: drafting fast, knowing their budget headroom, and tracking where their request
  is in the pipeline. They should only ever see their own unit's requisitions.
- **Procurement/finance officer** — the central reviewer who sees requisitions arriving
  from *every* unit, screens vendors, and clears or escalates them (the triage cockpit
  spec'd below). They need cross-unit visibility the requester should never have.

Audience overall: internal staff, SAP power-users, not consumers. They are used to
dense, information-rich tools (Fiori, SAP GUI, Excel) — so "sleek" here means
**disciplined density**, not whitespace-heavy startup minimalism. Avoid the SaaS-landing-page
look entirely; this is a working instrument, not a marketing page.

Reject generic defaults explicitly: no cream-background/serif-hero look, no near-black
page with one neon accent, no numbered "01/02/03" feature blocks. The requisition queue
itself — an ordered, timestamped, prioritized list — is the one place where numbering/
ordering is earned, because it's real sequence (queue position, risk rank), not decoration.

## 2. Design tokens

**Palette** — near-monochrome, cool graphite base (per existing brand), one deliberate
signal color reserved *only* for risk states:

- `--surface-base`: `#0B0D10` (near-black graphite, not pure black)
- `--surface-panel`: `#14171C` (glass panel fill, ~70% opacity over base with blur)
- `--surface-raised`: `#1C2027`
- `--stroke-hairline`: `#2A2F38` (1px borders, glass edges)
- `--text-primary`: `#E7E9EC`
- `--text-muted`: `#8B909B`
- `--accent-signal`: `#C9A24B` (muted brass/amber — reads as "SAP gold," used ONLY for
  risk flags, pending-review badges, and the agent's "thinking" state — never decorative)
- `--risk-critical`: `#B85450` (desaturated red-clay, not stock #FF0000)
- `--risk-clear`: `#5C8A72` (muted sage, not stock green)

Reasoning for the brass accent: it nods to SAP's enterprise-gold heritage without
literally reusing Fiori blue, and it gives you exactly one color that means "pay
attention," which is the entire point of a triage tool.

**Typography**:
- Display/headers: **IBM Plex Sans** (condensed weight for section headers) — enterprise
  lineage, pairs naturally with an SAP-adjacent product, not the templated Inter-everywhere look.
- Body/UI: **Inter** at 14px base — legible at data density.
- Data/mono (PR numbers, vendor IDs, amounts, timestamps): **IBM Plex Mono** — tabular
  figures, lets numbers align in columns like a ledger.

**Layout concept** — Fiori Launchpad-inspired shell, three fixed zones:

```
┌─────────────────────────────────────────────────────────┐
│ TOP BAR: org context · agent status pulse · search        │
├───────────┬─────────────────────────────┬─────────────────┤
│ QUEUE     │  FOCUSED REQUISITION         │  VENDOR         │
│ RAIL      │  (detail + agent reasoning   │  DOSSIER        │
│ (left,    │   trace, editable fields)    │  (right, slide  │
│ scrollable│                              │   panel)        │
│ tile list)│                              │                 │
├───────────┴─────────────────────────────┴─────────────────┤
│ BOTTOM STRIP: analytics ticker (spend, cycle time, flags)  │
└─────────────────────────────────────────────────────────┘
```

This is a **three-pane cockpit**, not a card grid. Left rail = queue (glass tiles,
ranked by risk score, brass dot for unreviewed). Center = the one requisition currently
being worked, including a visible **agent reasoning trace** (not hidden in a modal) —
this is the signature element (see below). Right = vendor dossier that slides in, not
a separate page — background-check results, past PO history, sanctions-list status,
financial health signal, all in one glass drawer.

## 3. Signature element

**The agent reasoning trace**, rendered as a vertical timeline inline in the center
panel — not a spinner, not a chat bubble. Each step the LangGraph pipeline actually
took (intake parse → vendor match → policy check → risk score) appears as a compact,
timestamped rail entry with a one-line justification in the agent's own words ("Vendor
tax ID matches a blocklisted entity from 2024 sanctions review — escalated"). This
turns the black-box AI decision into an auditable ledger entry, which is the actual
product differentiator (explainable procurement AI) — make it the thing this screen
is remembered for, not a decorative animation.

## 4. Key screens to spec in Cursor

### Requester side (unit dashboard)

1. **Unit Home** — the requester's landing view after login, scoped to their own cost
   center/department. Shows: budget headroom for the current period (a single clear
   number, not a chart — "₹4.2L of ₹6L used this quarter"), a status board of their own
   submitted PRs grouped by stage (Draft → Submitted → Under Review → Approved →
   PO Issued → Rejected), and a shortcut to start a new PR. This is a compact,
   lower-density view than the procurement cockpit — the requester doesn't need the
   agent's reasoning trace or cross-unit data, just "what did I ask for and where is it."
2. **PR Creation Wizard** — short, linear, minimal-chrome form: item/service details,
   quantity and estimated cost, cost center auto-filled from the logged-in unit,
   preferred vendor (optional — agent will suggest/validate one if left blank),
   justification. This is the one place a lighter, less dense layout is correct, since
   it's a single focused task, not a monitoring surface.
3. **My Requisitions** — a filterable list (status, date, amount) scoped to the
   requester's own unit only, each row expandable to show the same reasoning-trace
   timeline as the procurement view, but read-only — so a requester can see *why* their
   PR was flagged or delayed without being able to override it.

### Procurement/approver side (triage cockpit)

4. **Triage Queue** (default view for this persona) — ranked tile list across *all*
   units, brass dot = needs review, sage check = agent auto-cleared, clay flag =
   escalated. Filter by risk tier, requesting unit, department, amount.
5. **Requisition Detail + Reasoning Trace** — editable PR fields (SAP-style key-value
   grid, monospace values), agent trace timeline, approve/escalate/return actions. A
   visible "requesting unit" tag distinguishes where each PR originated.
6. **Vendor Dossier (slide panel)** — identity verification, sanctions/blocklist status,
   past performance (on-time %, dispute count), financial risk badge. Empty state for
   vendors with no history should read as "No prior transactions — first-time vendor,
   verify manually" (interface voice, states what to do next, not just "No data").

### Shared

7. **Analytics** — bottom strip expands to full view. Scoped by role: a requester sees
   their own unit's spend-by-category and cycle-time; procurement sees cross-unit spend,
   vendor risk distribution, and which units generate the most escalations. Use Recharts
   with the same token palette (brass only for flagged/anomalous series, everything else
   in graphite/sage neutrals).

## 5. Motion

One orchestrated moment: when the agent finishes screening a requisition, the reasoning
trace entries populate top-to-bottom in sequence (150ms stagger), ending with the
risk badge settling into place. No ambient background animation, no hover-bounce on
every tile — this is a work tool, restraint matters more than delight here.

## 6. Copy voice

Procurement-officer plain language, active voice, no marketing tone:
- Button: "Clear for approval" / "Escalate to finance" — not "Submit" / "Process"
- Error: "Vendor tax ID could not be verified — check the ID and retry" not "An error occurred"
- Empty queue: "Queue is clear. Nothing needs your review right now."

## 7. Technical notes for Cursor

- Build the shell as a persistent layout (`app/(dashboard)/layout.tsx`) with the
  three-pane grid; queue rail and vendor dossier are independently scrollable.
- Use CSS variables for every color (see tokens above) so the glassmorphism blur layers
  stay consistent — avoid hardcoded Tailwind color classes for anything in the palette.
- Recharts components should accept the token colors as props, not hardcoded hex, so
  analytics and triage views stay visually unified.
- Respect `prefers-reduced-motion` — disable the trace stagger animation, snap to final state.
