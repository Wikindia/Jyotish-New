"""
jyotish.dashas — timing systems.

Every system here is computed from the verified chart object, never from
approximated positions. Where a classical system has multiple published
variants, the variant implemented is named explicitly in the output so the
reading is auditable.

Systems:
  1. Vimshottari  — MD/AD/PD/Sookshma, from Moon's nakshatra, 120y, 365.25 d/y.
  2. Chara (Jaimini) — Rath variant: odd-footed (savya) direct counting,
     duration = count from sign to its lord (−1), lord in own sign = 12y,
     Scorpio/Aquarius co-lord chosen by strength (more conjunct planets, then
     higher degree).
  3. Narayana — Rath variant: seed = stronger of Lagna/7th, progression by
     modality (movable +1 / fixed +6 / dual +5), direction by odd/even-footed,
     duration = Chara counting with exaltation +1 / debilitation −1.
  4. Tajika varshaphal — true sidereal solar return via Swiss Ephemeris,
     Muntha, and Mudda dasha (Vimshottari order compressed to the solar year;
     first lord from nakshatra counted birth-star + completed years).
  5. Ashtottari (108y, BPHS ch.46 with Abhijit) — provided as the documented
     nakshatra-based cross-check system. See ASHTAMANGALA_NOTE.
"""
import datetime as dt
import swisseph as swe
from .core import (SIGNS, SIGN_LORDS, NAK_SPAN, NAK_LORDS, NAKSHATRAS,
                   ODD_FOOTED, MOVABLE, FIXED, DUAL, sign_of, deg_in_sign,
                   EXALTATION, DEBILITATION, jd_to_datetime)

YEAR_DAYS = 365.25

ASHTAMANGALA_NOTE = (
    "Ashtamangala in the Kerala tradition is a prasna (horary) framework: it "
    "requires a live prasna number/cowrie count and is not a natal dasha with a "
    "published birth-chart algorithm. Rather than invent one, this module "
    "provides Ashtottari dasha — the classical 108-year nakshatra dasha (BPHS "
    "ch. 46) widely used in Kerala practice as a cross-check on Vimshottari, "
    "including for marriage timing. It is labelled as Ashtottari in all output. "
    "Note: any earlier 'Ashtamangala dasha' statements made without this engine "
    "were not algorithmically grounded and should be treated as superseded."
)

# ---------------------------------------------------------------- Vimshottari
VIM_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
VIM_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
             "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}


def _subperiods(lord, start_jd, span_days, depth, max_depth, names):
    """Recursively split a period into 9 sub-periods in Vimshottari proportion."""
    periods = []
    idx = VIM_ORDER.index(lord)
    cursor = start_jd
    for i in range(9):
        sub = VIM_ORDER[(idx + i) % 9]
        sub_days = span_days * VIM_YEARS[sub] / 120.0
        entry = {"level": names[depth], "lord": sub,
                 "start_jd": cursor, "end_jd": cursor + sub_days,
                 "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                 "end": jd_to_datetime(cursor + sub_days).strftime("%Y-%m-%d")}
        if depth + 1 < max_depth:
            entry["sub"] = _subperiods(sub, cursor, sub_days, depth + 1, max_depth, names)
        periods.append(entry)
        cursor += sub_days
    return periods


def vimshottari(chart, levels=3, horizon_years=100):  # horizon counted FROM BIRTH
    """levels: 1=MD, 2=+AD, 3=+PD, 4=+Sookshma."""
    moon = chart["planets"]["Moon"]
    nak = moon["nakshatra"]
    lord = nak["lord"]
    elapsed_frac = nak["fraction_elapsed"]
    birth_jd = chart["meta"]["jd_ut"]
    names = ["Mahadasha", "Antardasha", "Pratyantardasha", "Sookshma"]

    md_days_full = VIM_YEARS[lord] * YEAR_DAYS
    balance_days = md_days_full * (1 - elapsed_frac)
    # first MD starts before birth so that remaining balance is correct
    start_jd = birth_jd - md_days_full * elapsed_frac

    timeline = []
    idx = VIM_ORDER.index(lord)
    cursor = start_jd
    total = 0
    i = 0
    while total < horizon_years * YEAR_DAYS + md_days_full:
        l = VIM_ORDER[(idx + i) % 9]
        span = VIM_YEARS[l] * YEAR_DAYS
        entry = {"level": "Mahadasha", "lord": l, "start_jd": cursor, "end_jd": cursor + span,
                 "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                 "end": jd_to_datetime(cursor + span).strftime("%Y-%m-%d")}
        if levels > 1:
            entry["sub"] = _subperiods(l, cursor, span, 1, levels, names)
        timeline.append(entry)
        cursor += span
        total += span
        i += 1
    return {"system": "Vimshottari", "moon_nakshatra": nak["name"],
            "balance_at_birth_years": round(balance_days / YEAR_DAYS, 3),
            "timeline": timeline}


def vim_period_at(vim, date, levels=3):
    """Return the chain of running periods (MD/AD/PD/...) on a given date."""
    jd = swe.julday(date.year, date.month, date.day, 12.0)
    chain = []
    node = {"sub": vim["timeline"]}
    for _ in range(levels):
        subs = node.get("sub")
        if not subs:
            break
        node = next((p for p in subs if p["start_jd"] <= jd < p["end_jd"]), None)
        if node is None:
            break
        chain.append({"level": node["level"], "lord": node["lord"],
                      "start": node["start"], "end": node["end"]})
    return chain


# ---------------------------------------------------------------- Jaimini Chara
def _stronger_colord(chart, sign):
    """Scorpio -> Mars/Ketu, Aquarius -> Saturn/Rahu. Strength: more planets in
    its sign of placement, then higher degree in sign (documented Rath rule)."""
    pair = ("Mars", "Ketu") if sign == 7 else ("Saturn", "Rahu")
    def score(pl):
        psign = chart["planets"][pl]["sign"]
        conj = sum(1 for g, d in chart["planets"].items() if d["sign"] == psign and g != pl)
        return (conj, chart["planets"][pl]["deg"])
    a, b = pair
    return a if score(a) >= score(b) else b


def _chara_duration(chart, sign):
    lord = SIGN_LORDS[sign]
    if sign in (7, 10):
        lord = _stronger_colord(chart, sign)
    lord_sign = chart["planets"][lord]["sign"]
    if lord_sign == sign:
        return 12, lord
    if sign in ODD_FOOTED:
        count = (lord_sign - sign) % 12 + 1
    else:
        count = (sign - lord_sign) % 12 + 1
    return count - 1, lord


def chara_dasha(chart, cycles=1):
    asc = chart["ascendant"]["sign"]
    direction = 1 if asc in ODD_FOOTED else -1
    birth_jd = chart["meta"]["jd_ut"]
    seq = [(asc + direction * i) % 12 for i in range(12)]
    timeline = []
    cursor = birth_jd
    for c in range(cycles):
        for s in seq:
            years, lord = _chara_duration(chart, s)
            if c > 0:
                years = 12 - years
            span = years * YEAR_DAYS
            ads = []
            ad_dir = 1 if s in ODD_FOOTED else -1
            ad_span = span / 12.0
            ad_cursor = cursor
            for j in range(12):
                ad_sign = (s + ad_dir * (j + 1)) % 12
                ads.append({"sign": ad_sign, "sign_name": SIGNS[ad_sign],
                            "start": jd_to_datetime(ad_cursor).strftime("%Y-%m-%d"),
                            "end": jd_to_datetime(ad_cursor + ad_span).strftime("%Y-%m-%d"),
                            "start_jd": ad_cursor, "end_jd": ad_cursor + ad_span})
                ad_cursor += ad_span
            timeline.append({"sign": s, "sign_name": SIGNS[s], "years": years,
                             "lord_used": lord,
                             "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                             "end": jd_to_datetime(cursor + span).strftime("%Y-%m-%d"),
                             "start_jd": cursor, "end_jd": cursor + span,
                             "antardashas": ads})
            cursor += span
    return {"system": "Chara (Jaimini, Rath variant)",
            "direction": "direct" if direction == 1 else "reverse", "timeline": timeline}


# ---------------------------------------------------------------- Narayana
def _sign_strength(chart, sign):
    occupants = [g for g, d in chart["planets"].items() if d["sign"] == sign]
    lord = SIGN_LORDS[sign] if sign not in (7, 10) else _stronger_colord(chart, sign)
    ld = chart["planets"][lord]
    dig_rank = {"exalted": 5, "moolatrikona": 4, "own sign": 3, "friend's sign": 2,
                "neutral sign": 1, "enemy's sign": 0, "debilitated": -1}
    return (len(occupants), dig_rank.get(ld["dignity"], 1), ld["deg"])


def narayana_dasha(chart, cycles=1):
    asc = chart["ascendant"]["sign"]
    seventh = (asc + 6) % 12
    seed = asc if _sign_strength(chart, asc) >= _sign_strength(chart, seventh) else seventh
    modality = seed % 3
    step = {MOVABLE: 1, FIXED: 6, DUAL: 5}[modality]
    direction = 1 if seed in ODD_FOOTED else -1
    birth_jd = chart["meta"]["jd_ut"]
    seq, s = [], seed
    for _ in range(12):
        seq.append(s)
        s = (s + direction * step) % 12
        # ensure all 12 signs covered (step 6 alone cycles only 2 signs; classical
        # progression: after returning to seed, shift by one — implemented below)
    # de-duplicate while preserving order; fill gaps by shifting seed
    seen, final = set(), []
    shift = 0
    s = seed
    while len(final) < 12:
        if s not in seen:
            seen.add(s); final.append(s)
            s = (s + direction * step) % 12
        else:
            shift += 1
            s = (seed + direction * shift) % 12
    timeline, cursor = [], birth_jd
    for c in range(cycles):
        for s in final:
            years, lord = _chara_duration(chart, s)
            dig = chart["planets"][lord]["dignity"]
            if dig == "exalted":
                years = min(years + 1, 12)
            elif dig == "debilitated":
                years = max(years - 1, 1)
            if c > 0:
                years = 12 - years
            span = years * YEAR_DAYS
            timeline.append({"sign": s, "sign_name": SIGNS[s], "years": years,
                             "lord_used": lord,
                             "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                             "end": jd_to_datetime(cursor + span).strftime("%Y-%m-%d"),
                             "start_jd": cursor, "end_jd": cursor + span})
            cursor += span
    return {"system": "Narayana (Rath variant)", "seed_sign": SIGNS[seed],
            "progression_step": step, "timeline": timeline}


# ---------------------------------------------------------------- Tajika
def solar_return_jd(chart, year):
    """JD (UT) when the sidereal Sun returns to its natal longitude in `year`."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    natal = chart["planets"]["Sun"]["lon"]
    b = chart["meta"]["birth"]
    by, bm, bd = (int(x) for x in b["date"].split("-"))
    guess = swe.julday(year, bm, bd, 12.0)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    lo, hi = guess - 3, guess + 3
    def diff(jd):
        pos, _ = swe.calc_ut(jd, swe.SUN, flags)
        return (pos[0] - natal + 180) % 360 - 180
    # bracket then bisect
    while diff(lo) > 0:
        lo -= 1
    while diff(hi) < 0:
        hi += 1
    for _ in range(60):
        mid = (lo + hi) / 2
        if diff(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def varshaphal(chart, year, lat=None, lon=None):
    """Annual (solar return) chart + Muntha + Mudda dasha for the year."""
    from .core import compute_chart, BirthData
    b = chart["meta"]["birth"]
    lat = lat if lat is not None else b["lat"]
    lon = lon if lon is not None else b["lon"]
    sr_jd = solar_return_jd(chart, year)
    y, m, d, h = swe.revjul(sr_jd)
    # build the varsha chart directly at the return moment (UT)
    hh = int(h); mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    vb = BirthData(y, m, d, hh, mm, 0, lat, lon, place=f"Solar return {year}")
    vchart = compute_chart(vb, node_type=chart["meta"]["node_type"])

    by = int(b["date"].split("-")[0])
    age = year - by  # completed years at this return
    natal_asc = chart["ascendant"]["sign"]
    muntha_sign = (natal_asc + age) % 12

    # Mudda dasha: Vimshottari order; first lord = lord of nakshatra counted
    # (birth star + completed years), i.e. index (birth_nak + age) % 27.
    birth_nak = chart["planets"]["Moon"]["nakshatra"]["index"]
    start_nak = (birth_nak + age) % 27
    start_lord = NAK_LORDS[start_nak]
    next_sr = solar_return_jd(chart, year + 1)
    year_len = next_sr - sr_jd
    idx = VIM_ORDER.index(start_lord)
    mudda, cursor = [], sr_jd
    for i in range(9):
        l = VIM_ORDER[(idx + i) % 9]
        span = year_len * VIM_YEARS[l] / 120.0
        mudda.append({"lord": l,
                      "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                      "end": jd_to_datetime(cursor + span).strftime("%Y-%m-%d"),
                      "start_jd": cursor, "end_jd": cursor + span})
        cursor += span
    return {"system": "Tajika varshaphal", "year": year,
            "solar_return_utc": jd_to_datetime(sr_jd).strftime("%Y-%m-%d %H:%M UT"),
            "varsha_chart": vchart,
            "muntha": {"sign": muntha_sign, "sign_name": SIGNS[muntha_sign],
                       "house_from_varsha_lagna":
                           ((muntha_sign - vchart["ascendant"]["sign"]) % 12) + 1},
            "mudda_dasha": mudda,
            "note": "Mudda first lord from nakshatra (birth star + completed years); "
                    "durations in Vimshottari proportion over the actual solar year."}


# ---------------------------------------------------------------- Ashtottari
# BPHS ch.46 allocation over 28 nakshatras (with Abhijit), starting from Ardra.
ASHT_ORDER = ["Sun", "Moon", "Mars", "Mercury", "Saturn", "Jupiter", "Rahu", "Venus"]
ASHT_YEARS = {"Sun": 6, "Moon": 15, "Mars": 8, "Mercury": 17, "Saturn": 10,
              "Jupiter": 19, "Rahu": 12, "Venus": 21}   # total 108
# groups of (3,4) alternating from Ardra
ASHT_GROUPS = [("Sun", 3), ("Moon", 4), ("Mars", 3), ("Mercury", 4),
               ("Saturn", 3), ("Jupiter", 4), ("Rahu", 3), ("Venus", 4)]

def _nak28(lon):
    """28-fold nakshatra index (Abhijit between U.Ashadha and Shravana)."""
    ABHIJIT_START = 276 + 40 / 60.0        # Capricorn 6°40'
    ABHIJIT_END = 280 + 53 / 60.0 + 20 / 3600.0  # Capricorn 10°53'20"
    if ABHIJIT_START <= lon < ABHIJIT_END:
        return 21, (lon - ABHIJIT_START) / (ABHIJIT_END - ABHIJIT_START)  # Abhijit
    idx27 = int(lon // NAK_SPAN) % 27
    frac = (lon % NAK_SPAN) / NAK_SPAN
    if idx27 < 21:
        return idx27, frac
    if idx27 == 20:  # U.Ashadha handled above threshold implicitly
        pass
    # after Abhijit slot, shift indices by +1 (Shravana=22 ... Revati=27)
    if lon >= ABHIJIT_END or idx27 >= 21:
        return idx27 + 1, frac
    return idx27, frac

def ashtottari(chart, horizon_years=90):
    moon_lon = chart["planets"]["Moon"]["lon"]
    idx28, frac = _nak28(moon_lon)
    # position counted from Ardra (27-index 5 -> 28-index 5)
    from_ardra = (idx28 - 5) % 28
    # walk groups to find lord + fraction within the lord's block
    cursor_naks = 0
    lord, blk_pos, blk_len = None, 0, 1
    for l, n in ASHT_GROUPS:
        if from_ardra < cursor_naks + n:
            lord, blk_pos, blk_len = l, from_ardra - cursor_naks, n
            break
        cursor_naks += n
    elapsed = (blk_pos + frac) / blk_len
    birth_jd = chart["meta"]["jd_ut"]
    start_jd = birth_jd - ASHT_YEARS[lord] * YEAR_DAYS * elapsed
    timeline, cursor = [], start_jd
    idx = ASHT_ORDER.index(lord)
    total = 0
    i = 0
    while total < horizon_years * YEAR_DAYS + 25 * YEAR_DAYS:
        l = ASHT_ORDER[(idx + i) % 8]
        span = ASHT_YEARS[l] * YEAR_DAYS
        ads, ad_cursor = [], cursor
        for j in range(8):
            sub = ASHT_ORDER[(ASHT_ORDER.index(l) + j) % 8]
            sspan = span * ASHT_YEARS[sub] / 108.0
            ads.append({"lord": sub,
                        "start": jd_to_datetime(ad_cursor).strftime("%Y-%m-%d"),
                        "end": jd_to_datetime(ad_cursor + sspan).strftime("%Y-%m-%d"),
                        "start_jd": ad_cursor, "end_jd": ad_cursor + sspan})
            ad_cursor += sspan
        timeline.append({"lord": l,
                         "start": jd_to_datetime(cursor).strftime("%Y-%m-%d"),
                         "end": jd_to_datetime(cursor + span).strftime("%Y-%m-%d"),
                         "start_jd": cursor, "end_jd": cursor + span,
                         "antardashas": ads})
        cursor += span
        total += span
        i += 1
    # classical applicability: Rahu (not in lagna) in a kendra/trikona from lagna lord
    lagna_lord = SIGN_LORDS[chart["ascendant"]["sign"]]
    ll_sign = chart["planets"][lagna_lord]["sign"]
    rahu_sign = chart["planets"]["Rahu"]["sign"]
    rel = (rahu_sign - ll_sign) % 12 + 1
    applicable = rel in (1, 4, 5, 7, 9, 10) and chart["planets"]["Rahu"]["house"] != 1
    return {"system": "Ashtottari (BPHS ch.46, with Abhijit)",
            "note": ASHTAMANGALA_NOTE,
            "classically_applicable": applicable,
            "applicability_rule": "Rahu in kendra/trikona from lagna lord, not in lagna",
            "timeline": timeline}
