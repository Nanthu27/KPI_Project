"""
Source-of-truth text for the User Guide, used both by the frontend's
UserGuidePopover component (kept in sync manually — see note below) and
by the Knowledge Agent's ingestion pipeline (app/rag/ingest.py).

NOTE on duplication: this text is also hard-coded in
frontend/src/components/UserGuidePopover.jsx for the on-screen popover.
Ideally the frontend would fetch this from a `/api/knowledge/user-guide`
endpoint instead of hard-coding it twice, removing the duplication risk
of the two copies drifting apart after an edit. That refactor is a small
follow-up, not done here to avoid an unrelated frontend change in this
backend-focused pass.
"""

USER_GUIDE_TEXT = """
### Introduction
This simulation leverages an interactive, traceable model that map key KPIs (or metrics) across
different levels (L1 and L2) to establish causal relationships with tech / process interventions,
and demonstrate how changes in operational metrics impact strategic business outcomes.

### Objective
Visualize interdependencies across operational metrics (Interventions -> L2 -> L1 -> Business Outcomes).
Analyze cascading impact of interventions on metrics and business outcomes.
Simulate baseline vs. ideal performance scenarios to estimate ROI.

### Components
Service Line Selection: Toggle buttons to view the metrics within selected service line.
Interventions: Process/Tech Interventions with a slider to input the scale of implementation across the in-scope function.
L2 Metrics: Base metrics mapped with selected service line and L1 Metrics. Sliders to modify values and impact higher level metrics.
L1 Metrics: Higher level metrics mapped with selected service line. Sliders to modify values and impact Business Outcomes.
Business Outcomes: End outcomes from a strategy pov. Static Sliders.
Benchmarks: Highlighted region on sliders.
Dependencies between metrics defined based on inversely / directly proportional relationships.
Calculations based on impact factor defined for the metric relationship.

### Key Assumptions
Benchmarks based on domain expertise and industry standards.
Metrics included are prioritized for business relevance, not exhaustive.
Impact factors reflect SME input and real-world implementations; may not fully reflect mathematical dependencies.
"""
