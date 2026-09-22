#!/usr/bin/env python3
"""make_demo.py — a complete synthetic run, so the template can be checked in
seconds without spending a cent.

Writes the clean/*.csv corpus a real run produces, plus state.json. Use it to
see the whole pipeline end to end before pointing it at a live URL, and to
verify a change to charts.py or build_pdf.py did not break the layout:

    python3 .claude/skills/positioning/assets/make_demo.py --out /tmp/pos-demo
    python3 .claude/skills/positioning/scripts/make_manifest.py --run /tmp/pos-demo
    cp .claude/skills/positioning/assets/manifest-example.json /tmp/pos-demo/report-manifest.json
    python3 .claude/skills/positioning/scripts/charts.py    --run /tmp/pos-demo
    python3 .claude/skills/positioning/scripts/build_pdf.py --run /tmp/pos-demo

The scaffold step is run against this corpus deliberately: it is how you check
that make_manifest.py still computes what the example manifest contains.
"""

import argparse
import csv
import json
import os

COMPS = ["ServiceTitan", "Housecall Pro", "Jobber", "Salesforce FS", "Excel"]

ALTERNATIVES = [
    ("ServiceTitan", "direct", "servicetitan.com", 60500, 22.40, "the category default for big shops", "SERP: hvac dispatch software"),
    ("Housecall Pro", "direct", "housecallpro.com", 33100, 18.10, "wins on price below 10 trucks", "SERP: hvac dispatch software"),
    ("Jobber", "direct", "getjobber.com", 27100, 16.80, "", "SERP: field service software"),
    ("Salesforce Field Service", "adjacent", "salesforce.com", 18100, 31.20, "arrives through an existing CRM deal", "SERP: field service management"),
    ("Google Calendar + texts", "adjacent", "", 9900, 2.10, "", "for-site: housecallpro.com"),
    ("Excel dispatch board", "diy", "", 8100, 1.40, "still the most common system at 10 trucks", "for-site: getjobber.com"),
    ("Whiteboard in the shop", "diy", "", 2400, 0.90, "", "SERP: dispatch board for hvac"),
    ("Owner does it from a truck", "nothing", "", 4400, 0.00, "the real incumbent under 15 trucks", "review mining"),
    ("Hire a dispatcher", "nothing", "", 6600, 4.30, "$52k/yr — this is the budget you compete for", "SERP: hvac dispatcher salary"),
]

ATTRIBUTES = [
    ("Auto-reshuffle when a job overruns", 1, [0, 0, 0, 0, 0], "unique", "no rival help centre documents an automatic reshuffle"),
    ("Texts every affected homeowner", 1, [0, 1, 0, 0, 0], "unique", "housecallpro.com/features — manual send only"),
    ("Live capacity forecast to end of week", 1, [0, 0, 0, 1, 0], "unique", ""),
    ("Skill-based technician matching", 1, [1, 0, 1, 1, 0], "table_stakes", ""),
    ("Drag-and-drop dispatch board", 1, [1, 1, 1, 1, 1], "table_stakes", ""),
    ("Mobile app for technicians", 1, [1, 1, 1, 1, 0], "table_stakes", ""),
    ("Route optimisation", 1, [1, 1, 1, 1, 0], "table_stakes", ""),
    ("Invoicing and payments", 0, [1, 1, 1, 1, 0], "gap", "every direct rival bundles it; you integrate instead"),
    ("QuickBooks sync", 1, [1, 1, 1, 0, 0], "table_stakes", ""),
    ("Customer portal", 0, [1, 1, 1, 1, 0], "gap", ""),
    ("Inventory tracking", 0, [1, 0, 1, 1, 0], "gap", ""),
    ("Sets up in an afternoon", 1, [0, 1, 1, 0, 1], "table_stakes", ""),
]

KEYWORDS = [
    ("field service management software", 210000, 24.10, "high", "Field service management"),
    ("field service software", 40500, 22.80, "high", "Field service management"),
    ("scheduling software", 33100, 12.40, "high", "Crew scheduling software"),
    ("crew scheduling software", 6600, 11.20, "medium", "Crew scheduling software"),
    ("hvac dispatch software", 14800, 18.40, "medium", "HVAC dispatch software"),
    ("hvac scheduling software", 8100, 17.60, "medium", "HVAC dispatch software"),
    ("dispatch software for hvac", 4400, 19.20, "medium", "HVAC dispatch software"),
    ("route planner", 22200, 9.80, "high", "Route planning software"),
    ("work order software", 12100, 14.30, "medium", "Field service management"),
    ("appointment reminder software", 8100, 6.40, "medium", "Appointment reminder software"),
    ("hvac dispatcher salary", 6600, 4.30, "low", ""),
    ("home services operating system", 720, 14.00, "low", "Home services operating system"),
    ("service orchestration", 260, 8.90, "low", ""),
    ("technician utilisation", 590, 7.20, "low", ""),
    ("route intelligence", 480, 6.10, "low", ""),
    ("field ops platform", 390, 9.40, "low", ""),
    ("job lifecycle", 210, 3.80, "low", ""),
    ("capacity planning", 720, 10.60, "low", ""),
    ("customer comms", 1300, 5.50, "low", ""),
]

FRAMES = [
    ("HVAC dispatch software", 27100, 18.40, 2, 86, 1, "two entrenched players, both generalists"),
    ("Field service management", 210000, 24.10, 9, 22, 0, "nine suites already own the term"),
    ("Crew scheduling software", 33100, 11.20, 6, 41, 0, ""),
    ("Route planning software", 22200, 9.80, 7, 28, 0, ""),
    ("Appointment reminder software", 8100, 6.40, 4, 63, 0, ""),
    ("Home services operating system", 720, 14.00, 1, 78, 0, "almost nobody searches this yet"),
]

CUSTOMERS = [
    ("Residential HVAC, 5–40 trucks", "reviews", 41, "the day repairs itself when a call runs long"),
    ("Residential HVAC, 5–40 trucks", "case_studies", 6, "the day repairs itself when a call runs long"),
    ("Residential HVAC, 5–40 trucks", "logo_wall", 12, ""),
    ("Residential HVAC, 5–40 trucks", "job_posts", 4, ""),
    ("Plumbing, 10–50 trucks", "reviews", 22, "emergency calls stop wrecking the schedule"),
    ("Plumbing, 10–50 trucks", "case_studies", 3, ""),
    ("Plumbing, 10–50 trucks", "logo_wall", 7, ""),
    ("Plumbing, 10–50 trucks", "job_posts", 1, ""),
    ("Electrical contractors", "reviews", 14, "permit-dependent jobs get sequenced right"),
    ("Electrical contractors", "case_studies", 2, ""),
    ("Electrical contractors", "logo_wall", 5, ""),
    ("Commercial facilities teams", "reviews", 9, "SLA clocks are visible on the board"),
    ("Commercial facilities teams", "case_studies", 4, ""),
    ("Commercial facilities teams", "logo_wall", 9, ""),
    ("Landscaping crews", "reviews", 6, "weather reshuffles the week in one click"),
    ("Landscaping crews", "logo_wall", 3, ""),
]

MESSAGING = [
    ("trailhead.example.com", "The day repairs itself after an overrun", "Your day fixes itself", "site"),
    ("trailhead.example.com", "No dispatcher required", "No dispatcher on staff? Good.", "site"),
    ("trailhead.example.com", "Promise a two-hour window and keep it", "Windows you can actually keep", "site"),
    ("trailhead.example.com", "Works offline in the field", "Works with no signal", "site"),
    ("Housecall Pro", "Promise a two-hour window and keep it", "On-my-way texts", "ad"),
    ("ServiceTitan", "Works offline in the field", "Offline mode for techs", "site"),
    ("ServiceTitan", "Grow your business", "Grow your home service business", "ad"),
    ("Housecall Pro", "Grow your business", "Built to grow your business", "ad"),
    ("Jobber", "Grow your business", "Grow with Jobber", "ad"),
    ("Salesforce FS", "Grow your business", "Scale field service", "site"),
    ("ServiceTitan", "All-in-one platform", "The all-in-one platform", "site"),
    ("Housecall Pro", "All-in-one platform", "Everything in one place", "site"),
    ("Jobber", "All-in-one platform", "One app for everything", "site"),
    ("Salesforce FS", "All-in-one platform", "One platform", "site"),
    ("ServiceTitan", "Get paid faster", "Get paid on the spot", "ad"),
    ("Housecall Pro", "Get paid faster", "Get paid faster", "ad"),
    ("Jobber", "Get paid faster", "Faster payments", "ad"),
    ("Housecall Pro", "Loved by 100,000 pros", "Trusted by 45,000 pros", "site"),
    ("Jobber", "Loved by 100,000 pros", "200,000 home service pros", "site"),
]

VOCABULARY = [
    ("service orchestration", "dispatch software", 260, 14800, "your own category word has almost no demand behind it"),
    ("technician utilisation", "scheduling software", 590, 33100, ""),
    ("route intelligence", "route planner", 480, 22200, ""),
    ("customer comms", "appointment reminder", 1300, 8100, ""),
    ("field ops platform", "field service software", 390, 40500, ""),
    ("job lifecycle", "work order software", 210, 12100, ""),
    ("capacity planning", "crew scheduling", 720, 6600, ""),
]


def write(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description="write a synthetic positioning run")
    p.add_argument("--out", default="/tmp/pos-demo")
    a = p.parse_args()
    run = a.out
    for sub in ("clean", "charts", "raw", "extract"):
        os.makedirs(os.path.join(run, sub), exist_ok=True)

    write(f"{run}/clean/alternatives.csv",
          ["name", "lane", "domain", "volume", "cpc", "note", "via"], ALTERNATIVES)

    write(f"{run}/clean/attributes.csv",
          ["attribute", "you"] + [f"comp_{c}" for c in COMPS] + ["verdict", "evidence"],
          [[n, y] + c + [v, e] for n, y, c, v, e in ATTRIBUTES])

    write(f"{run}/clean/keywords.csv",
          ["keyword", "search_volume", "cpc", "competition", "frame"], KEYWORDS)

    write(f"{run}/clean/frames.csv",
          ["frame", "demand_volume", "cpc", "density", "favorability", "recommended", "note"],
          FRAMES)

    # One row per artefact, the way a real run banks them: the scaffold's job is
    # to do the counting, so the demo must not pre-aggregate.
    cust_rows = []
    for seg, kind, n, praise in CUSTOMERS:
        for i in range(n):
            cust_rows.append([seg, kind, f"{kind} #{i+1} naming {seg}",
                              f"https://example.com/{kind}/{i+1}", praise if i == 0 else ""])
    write(f"{run}/clean/customers.csv",
          ["segment", "evidence_type", "evidence", "source_url", "praise_theme"], cust_rows)

    write(f"{run}/clean/messaging.csv",
          ["competitor", "theme", "claim", "source"], MESSAGING)

    write(f"{run}/clean/vocabulary.csv",
          ["yours", "theirs", "your_volume", "their_volume", "note"], VOCABULARY)

    with open(f"{run}/state.json", "w", encoding="utf-8") as f:
        json.dump({
            "slug": "trailhead", "url": "https://trailhead.example.com",
            "product_name": "Trailhead",
            "geo": {"location_code": 2840, "language_code": "en"},
            "budget": {"cap_usd": 6.0, "spent_usd": 5.62, "calls": []},
            "brightdata": {"day": "2026-08-23", "count": 11},
            "phase": "report", "nodes": {}, "assumptions": [],
        }, f, indent=2)

    print(f"demo run written to {run}")
    print("next:  make_manifest.py --run", run)


if __name__ == "__main__":
    main()
