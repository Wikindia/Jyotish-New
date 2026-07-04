"""
jyotish.yogas — classical yoga detection.

Every yoga is checked against its exact placement rule. A yoga is reported
only when the rule is satisfied by the calculated chart; each result carries
the evidence (the placements that satisfied the rule) so it can be audited.
"""
from .core import SIGNS, SIGN_LORDS, GRAHAS, OWN_SIGNS, EXALTATION

KENDRA = {1, 4, 7, 10}
TRIKONA = {1, 5, 9}
DUSTHANA = {6, 8, 12}


def _house_of(chart, planet):
    return chart["planets"][planet]["house"]

def _sign_of(chart, planet):
    return chart["planets"][planet]["sign"]

def _lord_of_house(chart, h):
    return chart["houses"][str(h)]["lord"]

def _conjunct(chart, a, b):
    return _sign_of(chart, a) == _sign_of(chart, b)

def _graha_aspects(chart, a, b):
    """Full sign aspects: all planets aspect 7th; Mars +4,+8; Jupiter +5,+9; Saturn +3,+10."""
    d = (_sign_of(chart, b) - _sign_of(chart, a)) % 12 + 1
    special = {"Mars": {4, 8}, "Jupiter": {5, 9}, "Saturn": {3, 10}}
    return d == 7 or d in special.get(a, set())

def _mutual_aspect(chart, a, b):
    return _graha_aspects(chart, a, b) and _graha_aspects(chart, b, a)

def _exchange(chart, a, b):
    return (_sign_of(chart, a) in OWN_SIGNS.get(b, []) and
            _sign_of(chart, b) in OWN_SIGNS.get(a, []))


def detect_yogas(chart):
    found = []
    P = chart["planets"]

    # --- Gajakesari: Jupiter in kendra from Moon
    dist = (P["Jupiter"]["sign"] - P["Moon"]["sign"]) % 12 + 1
    if dist in (1, 4, 7, 10):
        found.append({"yoga": "Gajakesari", "evidence":
                      f"Jupiter in {SIGNS[P['Jupiter']['sign']]} is {dist} signs from Moon in "
                      f"{SIGNS[P['Moon']['sign']]} (kendra from Moon)."})

    # --- Chandra-Mangala: Moon-Mars conjunction or mutual aspect
    if _conjunct(chart, "Moon", "Mars") or _mutual_aspect(chart, "Moon", "Mars"):
        how = "conjunct" if _conjunct(chart, "Moon", "Mars") else "in mutual aspect"
        found.append({"yoga": "Chandra-Mangala", "evidence": f"Moon and Mars {how}."})

    # --- Budhaditya: Sun-Mercury conjunction (Mercury not deeply combust noted)
    if _conjunct(chart, "Sun", "Mercury"):
        note = " (Mercury combust — yoga weakened)" if P["Mercury"].get("combust") else ""
        found.append({"yoga": "Budhaditya", "evidence":
                      f"Sun and Mercury conjunct in {SIGNS[P['Sun']['sign']]}{note}."})

    # --- Pancha Mahapurusha: Mars/Mercury/Jupiter/Venus/Saturn in own or
    #     exaltation sign AND in kendra from lagna
    mahapurusha = {"Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa",
                   "Venus": "Malavya", "Saturn": "Shasha"}
    for pl, name in mahapurusha.items():
        s, h = P[pl]["sign"], P[pl]["house"]
        if h in KENDRA and (s in OWN_SIGNS[pl] or s == EXALTATION[pl][0]):
            found.append({"yoga": f"{name} (Pancha Mahapurusha)", "evidence":
                          f"{pl} in {SIGNS[s]} ({P[pl]['dignity']}) in house {h} (kendra)."})

    # --- Raja yogas: kendra lord with trikona lord (conjunction, mutual aspect, exchange)
    kendra_lords = {_lord_of_house(chart, h) for h in KENDRA}
    trikona_lords = {_lord_of_house(chart, h) for h in TRIKONA}
    seen_pairs = set()
    for kl in kendra_lords:
        for tl in trikona_lords:
            if kl == tl:
                continue
            key = tuple(sorted((kl, tl)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if _conjunct(chart, kl, tl):
                found.append({"yoga": "Raja yoga", "evidence":
                              f"Kendra lord {kl} conjunct trikona lord {tl} in "
                              f"{SIGNS[P[kl]['sign']]} (house {P[kl]['house']})."})
            elif _exchange(chart, kl, tl):
                found.append({"yoga": "Raja yoga (parivartana)", "evidence":
                              f"Exchange between kendra lord {kl} and trikona lord {tl}."})
            elif _mutual_aspect(chart, kl, tl):
                found.append({"yoga": "Raja yoga (mutual aspect)", "evidence":
                              f"Kendra lord {kl} and trikona lord {tl} in mutual aspect."})

    # --- Dhana yogas: links between lords of 1,2,5,9,11
    dhana_houses = [1, 2, 5, 9, 11]
    dl = {h: _lord_of_house(chart, h) for h in dhana_houses}
    seen = set()
    for h1 in dhana_houses:
        for h2 in dhana_houses:
            if h1 >= h2 or dl[h1] == dl[h2]:
                continue
            key = tuple(sorted((dl[h1], dl[h2])))
            if key in seen:
                continue
            seen.add(key)
            if _conjunct(chart, dl[h1], dl[h2]) or _exchange(chart, dl[h1], dl[h2]):
                found.append({"yoga": "Dhana yoga", "evidence":
                              f"Lords of houses {h1} and {h2} ({dl[h1]}, {dl[h2]}) linked by "
                              f"{'conjunction' if _conjunct(chart, dl[h1], dl[h2]) else 'exchange'}."})

    # --- Vipareeta Raja: dusthana lord in a dusthana (other than its own house)
    for h in DUSTHANA:
        l = _lord_of_house(chart, h)
        lh = P[l]["house"]
        if lh in DUSTHANA:
            names = {6: "Harsha", 8: "Sarala", 12: "Vimala"}
            found.append({"yoga": f"Vipareeta Raja ({names[h]})", "evidence":
                          f"Lord of house {h} ({l}) placed in house {lh} (dusthana)."})

    # --- Neecha Bhanga for each debilitated planet
    for pl in GRAHAS:
        if P[pl]["dignity"] != "debilitated":
            continue
        s = P[pl]["sign"]
        dispositor = SIGN_LORDS[s]
        exalt_lord = next((p for p, (es, _) in EXALTATION.items()
                           if es == s and p not in ("Rahu", "Ketu")), None)
        reasons = []
        if P[dispositor]["house"] in KENDRA:
            reasons.append(f"dispositor {dispositor} in kendra from lagna (house {P[dispositor]['house']})")
        moon_sign = P["Moon"]["sign"]
        disp_from_moon = (P[dispositor]["sign"] - moon_sign) % 12 + 1
        if disp_from_moon in (1, 4, 7, 10):
            reasons.append(f"dispositor {dispositor} in kendra from Moon")
        if exalt_lord and P[exalt_lord]["house"] in KENDRA:
            reasons.append(f"exaltation lord of {SIGNS[s]} ({exalt_lord}) in kendra from lagna")
        # a planet exalted in the same sign occupying it
        cohab_exalt = next((p for p in GRAHAS if p != pl and P[p]["sign"] == s
                            and P[p]["dignity"] == "exalted"), None)
        if cohab_exalt:
            reasons.append(f"{cohab_exalt} exalted in the same sign")
        if reasons:
            found.append({"yoga": f"Neecha Bhanga ({pl})", "evidence":
                          f"{pl} debilitated in {SIGNS[s]}; cancellation via " + "; ".join(reasons) + "."})

    # --- Kemadruma: no planet (excl. Sun, Rahu, Ketu) in 2nd or 12th from Moon,
    #     none conjunct Moon; classical cancellation if planets in kendra from Moon
    moon_sign = P["Moon"]["sign"]
    flank = {(moon_sign + 1) % 12, (moon_sign - 1) % 12}
    others = [p for p in GRAHAS if p not in ("Moon", "Sun", "Rahu", "Ketu")]
    flanked = any(P[p]["sign"] in flank for p in others)
    with_moon = any(P[p]["sign"] == moon_sign for p in others)
    if not flanked and not with_moon:
        kendra_from_moon = any(((P[p]["sign"] - moon_sign) % 12 + 1) in (4, 7, 10)
                               for p in others)
        if kendra_from_moon:
            found.append({"yoga": "Kemadruma (cancelled)", "evidence":
                          "No planets flanking Moon, but planets occupy kendras from Moon "
                          "— Kemadruma bhanga applies."})
        else:
            found.append({"yoga": "Kemadruma", "evidence":
                          "No planets (excl. Sun/nodes) in 2nd/12th from Moon or with Moon."})

    return found
