"""
Synthetic dataset generator for Risk Radar.

Produces a rich, realistic stream of free-text project updates themed around a
Careem-style super-app (illustrative MOCK data — not real Careem data, and not
affiliated with or sourced from Careem) spanning multiple programs, projects,
teams, and ~10 weeks. Updates are deliberately *messy* — the kind of text that piles
up in standups, status emails and Jira comments — with risks, blockers and
cross-team dependencies planted throughout so the Risk Radar can be shown
catching them.

Every row also carries a hidden ground-truth label (`signal_truth`,
`severity_truth`). The Risk Radar never sees these — they exist only so the app
can report how well the AI classification matches the planted signal.

Run:  python generate_dataset.py
Out:  data/project_updates.csv  (deterministic; seeded)
"""

from __future__ import annotations

import csv
import os
import random
from datetime import date, timedelta

SEED = 42
START_MONDAY = date(2026, 3, 16)  # week 1 Monday
NUM_WEEKS = 10

# --------------------------------------------------------------------------- #
# Company structure — generic large enterprise, no real names.
# --------------------------------------------------------------------------- #

PEOPLE = [
    ("A. Khalil", "Eng Lead", "Payments"),
    ("M. Haddad", "Backend Eng", "Payments"),
    ("R. Sethi", "Product Manager", "Payments"),
    ("S. Rahman", "Eng Lead", "Captain"),
    ("J. Park", "Mobile Eng", "Captain"),
    ("L. Mansour", "Product Manager", "Captain"),
    ("T. Okeke", "Data Eng Lead", "Rides"),
    ("K. Aziz", "ML Eng", "Rides"),
    ("D. Costa", "Platform Eng Lead", "Cloud Infra"),
    ("N. Yusuf", "SRE", "Cloud Infra"),
    ("P. Haddadin", "Security Lead", "Security & Compliance"),
    ("E. Ramirez", "GRC Analyst", "Security & Compliance"),
    ("C. Nakamura", "Eng Lead", "Food"),
    ("F. El-Sayed", "Fullstack Eng", "Food"),
    ("G. Oyelaran", "Product Manager", "Food"),
    ("H. Vasquez", "Eng Lead", "Quik"),
    ("B. Kim", "Backend Eng", "Quik"),
    ("V. Ibrahim", "Growth PM", "Growth"),
    ("O. Lindgren", "Eng Lead", "Growth"),
    ("W. Achebe", "QA Lead", "Quality"),
    ("Z. Farouk", "Program Manager", "PMO"),
    ("Y. Fontaine", "Program Manager", "PMO"),
]

PEOPLE_BY_TEAM: dict[str, list[tuple[str, str, str]]] = {}
for p in PEOPLE:
    PEOPLE_BY_TEAM.setdefault(p[2], []).append(p)


# Each project belongs to a program and carries a "health storyline" weighting
# that biases how many risks/blockers it accumulates — so the portfolio shows a
# realistic mix of green, amber and red.
PROJECTS = [
    # program, project, owner_team, milestone, health
    ("Careem Pay", "Wallet Top-up & Cards", "Payments", "GA across UAE (Jun 30)", "red"),
    ("Careem Pay", "Send & Request Money", "Payments", "KSA launch (Jun 12)", "amber"),
    ("Rides", "Captain App 4.0", "Captain", "Public rollout (Jul 7)", "amber"),
    ("Rides", "Surge Pricing Engine v2", "Rides", "Eid readiness (Jun 20)", "green"),
    ("Careem Food", "Restaurant Onboarding Portal", "Food", "GA (Jun 23)", "amber"),
    ("Careem Food", "Live Order Tracking", "Food", "v2 ship (Jun 16)", "green"),
    ("Quik", "15-min Grocery Fulfilment", "Quik", "Dark-store launch (Jun 27)", "red"),
    ("Platform & Infrastructure", "Super-App Kubernetes Migration", "Cloud Infra", "Prod migration (Jul 1)", "amber"),
    ("Platform & Infrastructure", "API Gateway Consolidation", "Cloud Infra", "Cutover (Jun 18)", "green"),
    ("Trust & Safety", "PCI-DSS Compliance (Careem Pay)", "Security & Compliance", "Audit window (Jun 25)", "red"),
    ("Captain Experience", "Captain Earnings & Payouts", "Captain", "v1 (Jun 16)", "green"),
    ("Growth & Subscriptions", "Careem Plus Revamp", "Growth", "Campaign go-live (Jun 9)", "green"),
]

COMPONENTS = {
    "Wallet Top-up & Cards": ["the tokenization service", "the Emirates ID / KYC flow", "the bank top-up endpoint", "the card-issuance module", "the refunds flow"],
    "Send & Request Money": ["the P2P transfer flow", "the IBAN-linking step", "the transaction-limits engine", "the fraud-screening service"],
    "Captain App 4.0": ["the navigation shell", "the offline mode", "the earnings dashboard", "the trip-acceptance flow", "the in-app chat"],
    "Surge Pricing Engine v2": ["the demand-prediction model", "the zone heatmap", "the price-cap rules", "the surge-notification service"],
    "Restaurant Onboarding Portal": ["the menu-upload flow", "the document-verification step", "the commission-setup screen", "the restaurant dashboard"],
    "Live Order Tracking": ["the courier GPS pipeline", "the ETA model", "the push-notification service", "the live-map rendering"],
    "15-min Grocery Fulfilment": ["the inventory-sync job", "the picker app", "the dark-store routing", "the item-substitution logic"],
    "Super-App Kubernetes Migration": ["the service-mesh config", "the autoscaling policies", "the secrets-management setup", "the blue-green deploy pipeline"],
    "API Gateway Consolidation": ["the rate-limiting rules", "the auth middleware", "the canary routing", "the legacy-route shim"],
    "PCI-DSS Compliance (Careem Pay)": ["the cardholder-data scoping", "the access-review evidence", "the network-segmentation controls", "the incident-response runbook"],
    "Captain Earnings & Payouts": ["the payout-matching job", "the earnings ledger", "the instant-cashout flow", "the bank-statement importer"],
    "Careem Plus Revamp": ["the subscription engine", "the benefits catalog", "the billing integration", "the A/B testing module"],
}

# Cross-team dependency targets (team -> deliverable they owe others).
DEP_TARGETS = [
    ("Payments", "the Careem Pay API contract"),
    ("Security & Compliance", "production access sign-off"),
    ("Data", "the shared rider-identity dataset"),
    ("Cloud Infra", "the provisioned staging cluster"),
    ("Maps", "the routing & ETA service"),
    ("Platform", "the shared design-system components"),
]

VENDORS = ["the Emirates ID / KYC vendor", "the SMS OTP provider", "the card-network sandbox", "the maps & geocoding provider", "the bank settlement partner"]


# --------------------------------------------------------------------------- #
# Phrase banks per signal type. Each returns (text, severity_truth).
# --------------------------------------------------------------------------- #

def _on_track(comp, milestone, team):
    options = [
        (f"Sprint goals met — {comp} merged and deployed to staging, no issues. {milestone} still on track.", "low"),
        (f"Demo of {comp} to stakeholders went well; positive feedback. Tracking to plan.", "low"),
        (f"Wrapped {comp} ahead of schedule. QA sign-off received, nothing outstanding.", "low"),
        (f"Good week. {comp} is feature-complete and we even cleared some tech debt. Confident on {milestone}.", "low"),
        (f"All green on {comp}. Code review done, automated tests passing at 98% coverage.", "low"),
    ]
    return random.choice(options)


def _risk(comp, milestone, team):
    n = random.choice([1, 2, 3])
    options = [
        (f"Slightly concerned about {milestone} — {comp} is taking longer than estimated, could slip ~{n} week(s) if the current pace holds.", "medium"),
        (f"Load testing on {comp} is showing latency spikes under peak traffic. Not blocked yet, but this is a real risk to {milestone}.", "high"),
        (f"Scope for {comp} grew after the stakeholder review — three new requirements added. Risk of overrunning {milestone}.", "medium"),
        (f"Heads up: the engineer who owns {comp} is out on leave for {n} weeks. Bus-factor risk, no clear backup right now.", "high"),
        (f"We're seeing flaky test failures around {comp} that we can't reproduce locally. Worried it masks a deeper issue before {milestone}.", "medium"),
        (f"Estimate for {comp} was optimistic. Realistically I think we're trending behind on {milestone} — flagging early.", "high"),
        (f"Security review of {comp} surfaced a few findings. None critical yet, but remediation could eat into the {milestone} buffer.", "medium"),
    ]
    return random.choice(options)


def _blocker(comp, milestone, team):
    vendor = random.choice(VENDORS)
    dep_team, dep = random.choice(DEP_TARGETS)
    options = [
        (f"BLOCKED on {comp}: still waiting on {dep_team} for {dep}. We cannot proceed until this lands — escalating to the PMO.", "high"),
        (f"Hard blocker — {vendor} sandbox has been down for 4 days, so {comp} integration is completely untestable. {milestone} at risk.", "critical"),
        (f"{comp} is blocked: production access was not granted by Security. Raised a ticket last week, no movement yet.", "high"),
        (f"Critical blocker on {comp} — a data-migration step is corrupting records and we've had to halt the rollout entirely.", "critical"),
        (f"We are stuck on {comp}. The upstream {dep} from {dep_team} never arrived and our work is fully serialized behind it.", "high"),
        (f"Blocked: legal has not signed off on the {vendor} contract, so we can't even start the {comp} integration. Slipping {milestone}.", "critical"),
    ]
    return random.choice(options)


def _dependency(comp, milestone, team):
    dep_team, dep = random.choice(DEP_TARGETS)
    when = random.choice(["next week", "the following sprint", "late June", "an unknown date"])
    options = [
        (f"{comp} depends on {dep} from {dep_team}, which has now slipped to {when}. Coordinating revised timelines.", "medium"),
        (f"Cross-team dependency: {milestone} needs {dep} from {dep_team} before we can integrate. Tracking their ETA.", "medium"),
        (f"Waiting on {dep_team} to finalize {dep} before we can wire up {comp}. Not blocked today, but it's on the critical path.", "high"),
        (f"Reminder that {comp} can't ship without {dep} from {dep_team} — flagging so the dependency is visible at the program level.", "medium"),
    ]
    return random.choice(options)


# storyline -> (weighted signal distribution)
HEALTH_MIX = {
    "green": [("on_track", 0.80), ("dependency", 0.12), ("risk", 0.07), ("blocker", 0.01)],
    "amber": [("on_track", 0.48), ("dependency", 0.24), ("risk", 0.23), ("blocker", 0.05)],
    "red": [("on_track", 0.20), ("dependency", 0.22), ("risk", 0.34), ("blocker", 0.24)],
}

GEN = {
    "on_track": _on_track,
    "risk": _risk,
    "blocker": _blocker,
    "dependency": _dependency,
}


def _weighted_choice(mix):
    r = random.random()
    cum = 0.0
    for label, w in mix:
        cum += w
        if r <= cum:
            return label
    return mix[-1][0]


def generate_rows():
    random.seed(SEED)
    rows = []
    uid = 1
    for week in range(1, NUM_WEEKS + 1):
        monday = START_MONDAY + timedelta(weeks=week - 1)
        for program, project, owner_team, milestone, health in PROJECTS:
            mix = HEALTH_MIX[health]
            # 1–3 updates per project per week
            n_updates = random.choices([1, 2, 3], weights=[0.35, 0.45, 0.20])[0]
            for _ in range(n_updates):
                label = _weighted_choice(mix)
                comp = random.choice(COMPONENTS[project])
                text, severity = GEN[label](comp, milestone, owner_team)

                # author: mostly owner team, sometimes a PM or QA voice
                roll = random.random()
                if roll < 0.7 and owner_team in PEOPLE_BY_TEAM:
                    author, role, team = random.choice(PEOPLE_BY_TEAM[owner_team])
                elif roll < 0.85:
                    author, role, team = random.choice(PEOPLE_BY_TEAM["PMO"])
                else:
                    author, role, team = random.choice(PEOPLE_BY_TEAM["Quality"])

                # day within the work week
                day = monday + timedelta(days=random.randint(0, 4))

                rows.append({
                    "update_id": f"U{uid:04d}",
                    "week": week,
                    "date": day.isoformat(),
                    "program": program,
                    "project": project,
                    "milestone": milestone,
                    "author": author,
                    "role": role,
                    "team": team,
                    "update_text": text,
                    "signal_truth": label,
                    "severity_truth": severity,
                })
                uid += 1
    rows.sort(key=lambda r: (r["date"], r["update_id"]))
    return rows


def main():
    rows = generate_rows()
    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", "project_updates.csv")
    fields = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} updates across {len(PROJECTS)} projects to {out}")


if __name__ == "__main__":
    main()
