"""
jyotish.qa — question answering over a verified chart.

Pipeline per question:
  1. classify question -> domain (houses, karakas, relevant varga)
  2. read the ACTUAL calculated data for those houses/planets (never eyeballed)
  3. scan Vimshottari (AD/PD) + Chara + Narayana for periods connected to the
     domain; run Mudda dasha for the near-term year(s)
  4. report convergence across systems explicitly; report disagreement honestly
  5. flag birth-time sensitivity where the question is ascendant-dependent

Register: direct, specific, no horoscope-app filler. Tendencies, not certainties.
"""
import datetime as dt
import re
from .core import SIGNS, SIGN_LORDS, GRAHAS
from .dashas import vimshottari, chara_dasha, narayana_dasha, varshaphal, ashtottari, vim_period_at
from .yogas import detect_yogas

DOMAINS = {
    "marriage": {
        "keywords": ["marr", "wedding", "spouse", "wife", "husband",
                     "shaadi", "vivah", "engagement", "relationship", "partner",
                     "girlfriend", "boyfriend", "love"],
        "houses": [7, 2, 11], "karakas": ["Venus", "Jupiter"], "varga": "D9",
        "asc_sensitive": True},
    "career": {
        "keywords": ["career", "job", "promotion", "work", "profession", "switch",
                     "offer", "business", "startup", "role", "company", "boss",
                     "resign", "interview"],
        "houses": [10, 6, 11, 2], "karakas": ["Saturn", "Sun", "Mercury"],
        "varga": "D10", "asc_sensitive": True},
    "finance": {
        "keywords": ["money", "wealth", "finance", "financial", "income", "salary",
                     "bonus", "investment", "property", "buy", "purchase", "loan",
                     "debt", "gain"],
        "houses": [2, 11, 4], "karakas": ["Jupiter", "Venus"], "varga": None,
        "asc_sensitive": True},
    "health": {
        "keywords": ["health", "illness", "disease", "surgery", "injury", "fitness",
                     "medical", "hospital"],
        "houses": [1, 6, 8, 12], "karakas": ["Sun", "Moon", "Saturn"], "varga": None,
        "asc_sensitive": True},
    "children": {
        "keywords": ["child", "children", "kids", "son", "daughter", "pregnancy",
                     "santaan"],
        "houses": [5, 9], "karakas": ["Jupiter"], "varga": "D7", "asc_sensitive": True},
    "parents": {
        "keywords": ["father", "mother", "parents"],
        "houses": [4, 9], "karakas": ["Sun", "Moon"], "varga": "D12",
        "asc_sensitive": True},
    "foreign": {
        "keywords": ["abroad", "foreign", "overseas", "relocate", "migration", "visa"],
        "houses": [12, 9, 7], "karakas": ["Rahu"], "varga": None, "asc_sensitive": True},
    "litigation": {
        "keywords": ["legal", "court", "lawsuit", "dispute", "litigation", "enemy"],
        "houses": [6, 8], "karakas": ["Mars", "Saturn"], "varga": None,
        "asc_sensitive": True},
    "education": {
        "keywords": ["education", "study", "exam", "degree", "course", "mba", "learning"],
        "houses": [4, 5, 9], "karakas": ["Mercury", "Jupiter"], "varga": None,
        "asc_sensitive": True},
}


def classify(question):
    q = question.lower()
    scores = {}
    for name, d in DOMAINS.items():
        scores[name] = sum(1 for k in d["keywords"] if re.search(r"\b" + k, q))
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general", {"houses": [1, 9, 10], "karakas": ["Sun", "Moon"],
                           "varga": None, "asc_sensitive": True}
    return best, DOMAINS[best]


def _relevant_planets(chart, houses, karakas):
    """Planets connected to the domain: house lords, occupants, karakas."""
    rel = {}
    for h in houses:
        hd = chart["houses"][str(h)]
        rel.setdefault(hd["lord"], set()).add(f"lord of H{h}")
        for occ in hd["occupants"]:
            rel.setdefault(occ, set()).add(f"occupies H{h}")
    for k in karakas:
        rel.setdefault(k, set()).add("karaka")
    return {p: sorted(r) for p, r in rel.items()}


def _natal_promise(chart, houses, karakas, varga):
    lines = []
    for h in houses:
        hd = chart["houses"][str(h)]
        lord = hd["lord"]
        ld = chart["planets"][lord]
        occ = ", ".join(hd["occupants"]) if hd["occupants"] else "empty"
        lines.append(f"H{h} = {hd['sign_name']}, lord {lord} in H{ld['house']} "
                     f"({ld['str']}, {ld['dignity']}"
                     f"{', retrograde' if ld['retrograde'] else ''}"
                     f"{', combust' if ld.get('combust') else ''}). Occupants: {occ}.")
    for k in karakas:
        kd = chart["planets"][k]
        extra = []
        if kd.get("combust"):
            extra.append("combust")
        if kd["retrograde"]:
            extra.append("retrograde")
        if kd["vargottama"]:
            extra.append("vargottama")
        lines.append(f"Karaka {k}: {kd['str']}, H{kd['house']}, {kd['dignity']}"
                     f"{(' — ' + ', '.join(extra)) if extra else ''}.")
    if varga:
        vl = chart["varga_lagnas"][varga]
        lines.append(f"{varga} lagna: {vl['sign_name']}. Key planets in {varga}: " +
                     "; ".join(f"{k} in {chart['planets'][k]['vargas'][varga]['sign_name']}"
                               for k in karakas))
    return lines


def _vim_windows(chart, vim, rel_planets, start_date, years):
    """AD/PD windows in the horizon whose lords connect to the domain."""
    windows = []
    start_jd = _date_jd(start_date)
    end_jd = _date_jd(start_date + dt.timedelta(days=int(years * 365.25)))
    for md in vim["timeline"]:
        if md["end_jd"] < start_jd or md["start_jd"] > end_jd:
            continue
        for ad in md.get("sub", []):
            if ad["end_jd"] < start_jd or ad["start_jd"] > end_jd:
                continue
            ad_hit = ad["lord"] in rel_planets
            for pd in ad.get("sub", []):
                if pd["end_jd"] < start_jd or pd["start_jd"] > end_jd:
                    continue
                pd_hit = pd["lord"] in rel_planets
                if ad_hit and pd_hit:
                    windows.append({
                        "system": "Vimshottari",
                        "label": f"{md['lord']}/{ad['lord']}/{pd['lord']}",
                        "start": pd["start"], "end": pd["end"],
                        "start_jd": pd["start_jd"], "end_jd": pd["end_jd"],
                        "why": f"AD lord {ad['lord']} ({'; '.join(rel_planets[ad['lord']])}) "
                               f"and PD lord {pd['lord']} ({'; '.join(rel_planets[pd['lord']])})"})
            if ad_hit:
                windows.append({
                    "system": "Vimshottari",
                    "label": f"{md['lord']}/{ad['lord']} antardasha",
                    "start": ad["start"], "end": ad["end"],
                    "start_jd": ad["start_jd"], "end_jd": ad["end_jd"],
                    "why": f"AD lord {ad['lord']}: {'; '.join(rel_planets[ad['lord']])}"})
    return windows


def _sign_dasha_windows(chart, dasha, rel_planets, houses, start_date, years, use_ads=True):
    """Chara/Narayana periods whose sign holds a relevant house/planet, or whose lord is relevant."""
    windows = []
    asc = chart["ascendant"]["sign"]
    rel_signs = {(asc + h - 1) % 12 for h in houses}
    occupied_by_rel = {chart["planets"][p]["sign"] for p in rel_planets}
    start_jd = _date_jd(start_date)
    end_jd = _date_jd(start_date + dt.timedelta(days=int(years * 365.25)))
    for p in dasha["timeline"]:
        if p["end_jd"] < start_jd or p["start_jd"] > end_jd:
            continue
        s = p["sign"]
        reasons = []
        if s in rel_signs:
            h = (s - asc) % 12 + 1
            reasons.append(f"dasha sign {SIGNS[s]} is H{h}")
        if s in occupied_by_rel:
            occ = [q for q in rel_planets if chart["planets"][q]["sign"] == s]
            reasons.append(f"holds {', '.join(occ)}")
        if p.get("lord_used") in rel_planets:
            reasons.append(f"dasha lord {p['lord_used']} is domain-relevant")
        if reasons:
            windows.append({"system": dasha["system"].split(" ")[0],
                            "label": f"{p['sign_name']} dasha",
                            "start": p["start"], "end": p["end"],
                            "start_jd": p["start_jd"], "end_jd": p["end_jd"],
                            "why": "; ".join(reasons)})
    return windows


def _date_jd(d):
    import swisseph as swe
    return swe.julday(d.year, d.month, d.day, 12.0)


def _overlap(a, b):
    lo = max(a["start_jd"], b["start_jd"])
    hi = min(a["end_jd"], b["end_jd"])
    return (lo, hi) if hi > lo else None


def find_convergence(windows):
    """Date ranges where windows from >=2 different systems overlap."""
    conv = []
    for i in range(len(windows)):
        for j in range(i + 1, len(windows)):
            a, b = windows[i], windows[j]
            if a["system"] == b["system"]:
                continue
            ov = _overlap(a, b)
            if ov:
                from .core import jd_to_datetime
                conv.append({"start": jd_to_datetime(ov[0]).strftime("%Y-%m-%d"),
                             "end": jd_to_datetime(ov[1]).strftime("%Y-%m-%d"),
                             "start_jd": ov[0], "end_jd": ov[1],
                             "systems": sorted({a["system"], b["system"]}),
                             "details": [f"{a['system']}: {a['label']} ({a['why']})",
                                         f"{b['system']}: {b['label']} ({b['why']})"]})
    conv.sort(key=lambda c: c["start_jd"])
    # merge near-identical overlaps
    merged = []
    for c in conv:
        if merged and abs(c["start_jd"] - merged[-1]["start_jd"]) < 20 and \
           abs(c["end_jd"] - merged[-1]["end_jd"]) < 20:
            merged[-1]["systems"] = sorted(set(merged[-1]["systems"]) | set(c["systems"]))
            merged[-1]["details"] += [d for d in c["details"] if d not in merged[-1]["details"]]
        else:
            merged.append(c)
    return merged


def answer(chart, question, today=None, horizon_years=5):
    today = today or dt.date.today()
    domain, spec = classify(question)
    rel = _relevant_planets(chart, spec["houses"], spec["karakas"])

    vim = vimshottari(chart, levels=3)
    chara = chara_dasha(chart, cycles=2)
    naray = narayana_dasha(chart, cycles=2)
    asht = ashtottari(chart)

    windows = []
    windows += _vim_windows(chart, vim, rel, today, horizon_years)
    windows += _sign_dasha_windows(chart, chara, rel, spec["houses"], today, horizon_years)
    windows += _sign_dasha_windows(chart, naray, rel, spec["houses"], today, horizon_years)
    convergence = find_convergence(windows)

    yogas = detect_yogas(chart)
    domain_yogas = [y for y in yogas if any(
        k in y["evidence"] for k in rel)] if rel else yogas

    current = vim_period_at(vim, today, levels=3)

    report = {
        "question": question,
        "domain": domain,
        "asc_caution": None if chart["meta"]["asc_stable_pm5min"] or not spec["asc_sensitive"]
        else ("Ascendant sign changes within ±5 minutes of the stated birth time. "
              "House-based conclusions below carry that uncertainty."),
        "relevant_factors": rel,
        "natal_promise": _natal_promise(chart, spec["houses"], spec["karakas"], spec["varga"]),
        "current_dasha": current,
        "windows": sorted(windows, key=lambda w: w["start_jd"])[:20],
        "convergence": convergence[:10],
        "yogas_present": domain_yogas,
        "ashtottari_applicable": asht["classically_applicable"],
        "register_note": "Tendency, not certainty. Windows are where multiple "
                         "independent systems point the same way.",
    }
    return report


def render(report):
    L = []
    L.append(f"QUESTION: {report['question']}   [domain: {report['domain']}]")
    if report["asc_caution"]:
        L.append(f"⚠ {report['asc_caution']}")
    L.append("\n— Natal promise —")
    L += ["  " + x for x in report["natal_promise"]]
    L.append("\n— Currently running (Vimshottari) —")
    L.append("  " + " > ".join(f"{c['lord']} {c['level'][:2]} (to {c['end']})"
                               for c in report["current_dasha"]))
    if report["convergence"]:
        L.append("\n— CONVERGENCE (≥2 independent systems overlap) —")
        for c in report["convergence"]:
            L.append(f"  {c['start']} → {c['end']}  [{' + '.join(c['systems'])}]")
            for d in c["details"]:
                L.append(f"      · {d}")
    else:
        L.append("\n— No multi-system convergence in the horizon. The systems "
                 "do not agree on a single window; treating any one system's "
                 "window as decisive would be cherry-picking. —")
    L.append("\n— All flagged windows —")
    for w in report["windows"]:
        L.append(f"  {w['start']} → {w['end']}  {w['system']}: {w['label']}  ({w['why']})")
    if report["yogas_present"]:
        L.append("\n— Yogas bearing on this question —")
        for y in report["yogas_present"]:
            L.append(f"  {y['yoga']}: {y['evidence']}")
    L.append(f"\n{report['register_note']}")
    return "\n".join(L)
