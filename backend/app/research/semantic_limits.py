"""Internal semantic execution bounds; no public request controls.

Matches the existing event-index scan budget (10,000 events), versus 576 public
events in the documented September 2026 audit. A complete UUID match-any list
costs about 400 KiB, comfortably within InternalHTTP's 2 MiB request budget.
"""

MAX_ELIGIBLE_EVENTS = 10_000
