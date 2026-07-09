"""
Seed data.

Sourced from the project's "Level-wise Parameters" / "updated version-
relationship" sheets, scoped to Finance & Accounting > Order to Cash,
and tuned so the default (0% intervention) state renders identically
to the provided screenshots:

  Business Outcome : Cash Conversion Cycle (Days)   10 / 45(target) / 60, default 50
  L1 Metrics        : Days Sales Outstanding (DSO)   1 / 45 / 60,   default 45
                      Bad Debt Ratio (%)             0 / 2  / 10,   default 2
                      Collection Efficiency (%)      40 / 90 / 100, default 70
  L2 Metrics        : Invoice Processing Cycle Time  1 / 8  / 30,   default 8
                      First-Time Match Rate (%)      40 / 90 / 100, default 70
                      Collection Efficiency (%)      40 / 90 / 100, default 70
  Interventions     : Intelligent Document Processing  0
                      RPA Bots                         0
                      Workflow Automation              0

Impact factors are carried over from the "updated version-relationship"
and "Interventions impacting L2" / "Relationships" sheets (the sign
indicates whether the link increases or decreases the upstream metric).
"""
from sqlalchemy.orm import Session

from .models import BusinessOutcome, L1Metric, L2Metric, Intervention, Vertical, LOB as LOBModel, User
from .database import SessionLocal, engine, Base


def seed(db: Session) -> None:
    if db.query(BusinessOutcome).count() > 0:
        return  # already seeded

    VH = "Finance & Accounting"
    LOB = "Order to Cash"

    # --- Business Outcome ------------------------------------------------
    ccc = BusinessOutcome(
        name="Cash Conversion Cycle",
        unit="Days",
        min_value=10, band_min=30, target_value=45, max_value=60,
        default_value=50, current_value=50, improvement_percentage=0,
        higher_is_better=0,  # lower CCC is better
        vertical_horizontal=VH, lob=LOB, sort_order=0,
    )
    db.add(ccc)
    db.commit()
    db.refresh(ccc)

    # --- L1 Metrics --------------------------------------------------------
    dso = L1Metric(
        name="Days Sales Outstanding (DSO)", unit="Days",
        min_value=1, band_min=30, target_value=45, max_value=60,
        default_value=45, current_value=45, improvement_percentage=0,
        higher_is_better=0,
        vertical_horizontal=VH, lob=LOB, sort_order=0,
    )
    bad_debt = L1Metric(
        name="Bad Debt Ratio", unit="%",
        min_value=0, band_min=0, target_value=2, max_value=10,
        default_value=2, current_value=2, improvement_percentage=0,
        higher_is_better=0,
        vertical_horizontal=VH, lob=LOB, sort_order=1,
    )
    collection_eff_l1 = L1Metric(
        name="Collection Efficiency", unit="%",
        min_value=40, band_min=90, target_value=100, max_value=100,
        default_value=70, current_value=70, improvement_percentage=0,
        higher_is_better=1,
        vertical_horizontal=VH, lob=LOB, sort_order=2,
    )
    db.add_all([dso, bad_debt, collection_eff_l1])
    db.commit()
    for m in (dso, bad_debt, collection_eff_l1):
        db.refresh(m)

    # L1 -> Business Outcome links (impact factors per BRD "Relationships (L1 impacting BO)")
    from .repositories import l1_metric_repo
    l1_metric_repo.set_business_outcome_links(db, dso.id, [{"business_outcome_id": ccc.id, "impact_factor": -0.275}])
    l1_metric_repo.set_business_outcome_links(db, bad_debt.id, [{"business_outcome_id": ccc.id, "impact_factor": -0.05}])
    l1_metric_repo.set_business_outcome_links(db, collection_eff_l1.id, [{"business_outcome_id": ccc.id, "impact_factor": -0.166}])

    # --- L2 Metrics ----------------------------------------------------------
    invoice_cycle = L2Metric(
        name="Invoice Processing Cycle Time", unit="Days",
        min_value=1, band_min=3, target_value=7, max_value=30,
        default_value=8, current_value=8, improvement_percentage=0,
        higher_is_better=0,
        vertical_horizontal=VH, lob=LOB, sort_order=0,
    )
    first_time_match = L2Metric(
        name="First-Time Match Rate", unit="%",
        min_value=40, band_min=80, target_value=100, max_value=100,
        default_value=70, current_value=70, improvement_percentage=0,
        higher_is_better=1,
        vertical_horizontal=VH, lob=LOB, sort_order=1,
    )
    collection_eff_l2 = L2Metric(
        name="Collection Efficiency", unit="%",
        min_value=40, band_min=90, target_value=100, max_value=100,
        default_value=70, current_value=70, improvement_percentage=0,
        higher_is_better=1,
        vertical_horizontal=VH, lob=LOB, sort_order=2,
    )
    db.add_all([invoice_cycle, first_time_match, collection_eff_l2])
    db.commit()
    for m in (invoice_cycle, first_time_match, collection_eff_l2):
        db.refresh(m)

    from .repositories import l2_metric_repo
    # L2 -> L1 links
    l2_metric_repo.set_l1_links(db, invoice_cycle.id, [{"l1_metric_id": dso.id, "impact_factor": -0.25}])
    l2_metric_repo.set_l1_links(db, first_time_match.id, [{"l1_metric_id": bad_debt.id, "impact_factor": -0.05}])
    l2_metric_repo.set_l1_links(db, collection_eff_l2.id, [{"l1_metric_id": collection_eff_l1.id, "impact_factor": 0.1667}])

    # --- Interventions ---------------------------------------------------
    # Risk/cost/effort/confidence below are illustrative admin-configured
    # values (see decision_engine.py) — NOT derived from the BRD, which
    # (per the benchmark-range discussion) does not define these. They
    # exist so Decision Advisor / Goal Agent scenario scoring has real
    # metadata to weight instead of an LLM guessing "this seems risky".
    # An admin should review/adjust these via the Structure & Access
    # Control screens before relying on them for real decisions.
    idp = Intervention(
        name="Intelligent Document Processing", percentage=0,
        description="Uses OCR + AI to auto-extract, validate, and process invoices, POs, and contracts",
        vertical_horizontal=VH, lob=LOB, sort_order=0,
        risk_level="High", cost_level="High", effort_weeks=16, confidence_pct=85,
    )
    rpa = Intervention(
        name="RPA Bots", percentage=0,
        description="Automated PO generation, routing, and payment reminders",
        vertical_horizontal=VH, lob=LOB, sort_order=1,
        risk_level="Medium", cost_level="Medium", effort_weeks=8, confidence_pct=92,
    )
    workflow = Intervention(
        name="Workflow Automation", percentage=0,
        description="Standardizes invoice approvals and expense management with automated routing",
        vertical_horizontal=VH, lob=LOB, sort_order=2,
        risk_level="Low", cost_level="Low", effort_weeks=4, confidence_pct=95,
    )
    db.add_all([idp, rpa, workflow])
    db.commit()
    for m in (idp, rpa, workflow):
        db.refresh(m)

    from .repositories import intervention_repo
    # Intervention -> L2 links (impact factors from "updated version-relationship" sheet)
    intervention_repo.set_l2_links(db, idp.id, [{"l2_metric_id": invoice_cycle.id, "impact_factor": -0.10}])
    intervention_repo.set_l2_links(db, rpa.id, [
        {"l2_metric_id": invoice_cycle.id, "impact_factor": -0.20},
        {"l2_metric_id": first_time_match.id, "impact_factor": 0.20},
    ])
    intervention_repo.set_l2_links(db, workflow.id, [{"l2_metric_id": invoice_cycle.id, "impact_factor": -0.15}])

    db.commit()

    # --- Verticals / LOBs (Structure & Access Control > Mapping) ----------
    # Matches the dropdown options shown in the product screenshots so the
    # Vertical/Horizontal and LOB selects have real, manageable entries
    # rather than just whatever strings happen to exist on metric rows.
    fa = Vertical(name="Finance & Accounting")
    db.add(fa)
    db.commit()
    db.refresh(fa)
    db.add_all([
        LOBModel(name="Order to Cash", vertical_id=fa.id),
        LOBModel(name="Procure to Pay", vertical_id=fa.id),
        LOBModel(name="Record to Report", vertical_id=fa.id),
    ])

    tco = Vertical(name="TCO Estimator")
    db.add(tco)
    db.commit()
    db.refresh(tco)
    db.add_all([
        LOBModel(name="Year 1", vertical_id=tco.id),
        LOBModel(name="Year 2", vertical_id=tco.id),
        LOBModel(name="Year 3", vertical_id=tco.id),
    ])

    sales = Vertical(name="Sales")
    db.add(sales)
    db.commit()
    db.refresh(sales)
    db.add_all([
        LOBModel(name="Inbound Sales", vertical_id=sales.id),
        LOBModel(name="Outbound Sales", vertical_id=sales.id),
    ])

    godaddy = Vertical(name="Godaddy Sales Program")
    db.add(godaddy)
    db.commit()
    db.refresh(godaddy)
    db.add(LOBModel(name="Sales", vertical_id=godaddy.id))

    db.commit()

    # --- Sample onboarded users --------------------------------------------
    db.add_all([
        User(name="Pratheek Basrithaya", email="basrithaya.5@apac.teleperformance.com", role="Admin"),
        User(name="Nithesh", email="saini.1569@apac.teleperformance.com", role="Admin"),
        User(name="Udit", email="chauhan.1860@teleperformanceusa.com", role="Admin"),
        User(name="Himadri Sarkar", email="Himadri.Sarkar@tp.com", role="Admin"),
    ])
    db.commit()


def run_seed() -> None:
    Base.metadata.create_all(bind=engine)
    from .migrations import run_lightweight_migrations
    run_lightweight_migrations(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
    print("Seed complete.")
