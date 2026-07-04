"""
MANDATORY verification: the reference chart must pass before anything else runs.
13 June 1999, 13:33 IST, Kota (25.2138N, 75.8648E). Lahiri, Whole Sign.

Signs and houses must match EXACTLY. Degrees must match the confirmed integer
degree (truncation convention) within tolerance. Rahu note: the confirmed
reference degree 21° corresponds to the MEAN node (21°54'); true node gives
20°21'. Both are Cancer / Ashlesha / H11. The test asserts both node modes.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jyotish.core import BirthData, compute_chart

BIRTH = BirthData(1999, 6, 13, 13, 33, 5.5, 25.2138, 75.8648, "Kota, Rajasthan")

EXPECTED = {  # planet: (sign_name, integer_deg, house)
    "Sun": ("Taurus", 28, 9), "Moon": ("Taurus", 21, 9), "Mars": ("Libra", 1, 2),
    "Mercury": ("Gemini", 17, 10), "Jupiter": ("Aries", 3, 8),
    "Venus": ("Cancer", 13, 11), "Saturn": ("Aries", 18, 8),
    "Ketu": ("Capricorn", None, 5),
}

def run():
    failures = []
    chart = compute_chart(BIRTH, node_type="true")

    if chart["ascendant"]["sign_name"] != "Virgo":
        failures.append(f"Ascendant sign: got {chart['ascendant']['sign_name']}, want Virgo")
    if abs(chart["ascendant"]["deg"] - 14) > 1.0:
        failures.append(f"Ascendant degree {chart['ascendant']['deg']:.2f} not within 1° of 14")

    for pl, (sname, ideg, house) in EXPECTED.items():
        p = chart["planets"][pl]
        if p["sign_name"] != sname:
            failures.append(f"{pl} sign: got {p['sign_name']}, want {sname}")
        if p["house"] != house:
            failures.append(f"{pl} house: got {p['house']}, want {house}")
        if ideg is not None and int(p["deg"]) != ideg:
            failures.append(f"{pl} degree: got {p['deg']:.2f} (int {int(p['deg'])}), want {ideg}")

    # Rahu: sign/house must match in BOTH node modes; degree 21 matches mean node
    for mode, want_int_ok in (("true", False), ("mean", True)):
        c = compute_chart(BIRTH, node_type=mode)
        r = c["planets"]["Rahu"]
        if r["sign_name"] != "Cancer" or r["house"] != 11:
            failures.append(f"Rahu ({mode} node): got {r['sign_name']} H{r['house']}, want Cancer H11")
        if r["nakshatra"]["name"] != "Ashlesha":
            failures.append(f"Rahu ({mode} node) nakshatra: got {r['nakshatra']['name']}, want Ashlesha")
        if want_int_ok and int(r["deg"]) != 21:
            failures.append(f"Rahu (mean node) degree {r['deg']:.2f}: confirmed ref is 21")

    # confirmed dignity statuses
    c = compute_chart(BIRTH)
    checks = [("Moon", "exalted"), ("Saturn", "debilitated")]
    for pl, dig in checks:
        if c["planets"][pl]["dignity"] != dig:
            failures.append(f"{pl} dignity: got {c['planets'][pl]['dignity']}, want {dig}")
    if not c["planets"]["Mars"]["vargottama"]:
        failures.append("Mars vargottama: expected True (Libra in D1 and D9)")
    if c["planets"]["Moon"]["nakshatra"]["name"] != "Rohini":
        failures.append(f"Moon nakshatra: got {c['planets']['Moon']['nakshatra']['name']}, want Rohini")

    if failures:
        print("REFERENCE CHART VERIFICATION FAILED:")
        for f in failures:
            print("  ✗", f)
        sys.exit(1)
    print("REFERENCE CHART VERIFICATION PASSED — all signs, houses, degrees, "
          "dignities, Rohini Moon, Mars vargottama confirmed.")

if __name__ == "__main__":
    run()
