"""
jyotish.core — chart calculation engine.

All planetary positions come from the Swiss Ephemeris (pyswisseph) with bundled
.se1 data files. NOTHING in this module approximates a planetary position.

Defaults (per spec):
  - Lahiri ayanamsha (sidereal)
  - Whole Sign houses
  - True node for Rahu/Ketu (config option node_type='mean' available;
    note: the human-confirmed reference chart's Rahu degree matches the mean node)
"""
import os
import hashlib
import json
import datetime as dt
import swisseph as swe

EPHE_PATH = os.environ.get(
    "JYOTISH_EPHE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ephe")
)
swe.set_ephe_path(EPHE_PATH)

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

SIGN_LORDS = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus",
              "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
              "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
              "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
              "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
              "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
              "Uttara Bhadrapada", "Revati"]

NAK_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn",
             "Mercury"] * 3  # 27 nakshatras, 9-lord cycle starting Ashwini=Ketu

NAK_SPAN = 360.0 / 27.0  # 13°20'

PLANET_IDS = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
              "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
              "Venus": swe.VENUS, "Saturn": swe.SATURN}

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

# --- dignity tables -----------------------------------------------------------
EXALTATION = {"Sun": (0, 10), "Moon": (1, 3), "Mars": (9, 28), "Mercury": (5, 15),
              "Jupiter": (3, 5), "Venus": (11, 27), "Saturn": (6, 20),
              "Rahu": (1, None), "Ketu": (7, None)}   # (sign index, deep exaltation degree)
DEBILITATION = {p: ((s + 6) % 12, d) for p, (s, d) in EXALTATION.items()}
OWN_SIGNS = {"Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5],
             "Jupiter": [8, 11], "Venus": [1, 6], "Saturn": [9, 10],
             "Rahu": [], "Ketu": []}
MOOLATRIKONA = {"Sun": (4, 0, 20), "Moon": (1, 3, 30), "Mars": (0, 0, 12),
                "Mercury": (5, 16, 20), "Jupiter": (8, 0, 10),
                "Venus": (6, 0, 15), "Saturn": (10, 0, 20)}
NATURAL_FRIENDS = {
    "Sun": {"friends": ["Moon", "Mars", "Jupiter"], "enemies": ["Venus", "Saturn"]},
    "Moon": {"friends": ["Sun", "Mercury"], "enemies": []},
    "Mars": {"friends": ["Sun", "Moon", "Jupiter"], "enemies": ["Mercury"]},
    "Mercury": {"friends": ["Sun", "Venus"], "enemies": ["Moon"]},
    "Jupiter": {"friends": ["Sun", "Moon", "Mars"], "enemies": ["Mercury", "Venus"]},
    "Venus": {"friends": ["Mercury", "Saturn"], "enemies": ["Sun", "Moon"]},
    "Saturn": {"friends": ["Mercury", "Venus"], "enemies": ["Sun", "Moon", "Mars"]},
    "Rahu": {"friends": ["Venus", "Saturn", "Mercury"], "enemies": ["Sun", "Moon", "Mars"]},
    "Ketu": {"friends": ["Mars", "Venus", "Saturn"], "enemies": ["Sun", "Moon"]},
}
COMBUSTION_ORB = {"Moon": 12, "Mars": 17, "Mercury": 14, "Jupiter": 11,
                  "Venus": 10, "Saturn": 15}
COMBUSTION_ORB_RETRO = {"Mercury": 12, "Venus": 8}

MOVABLE, FIXED, DUAL = 0, 1, 2  # sign % 3

# odd-footed (savya) signs per Jaimini: Aries–Gemini, Libra–Sagittarius
ODD_FOOTED = {0, 1, 2, 6, 7, 8}


def sign_of(lon):
    return int(lon // 30) % 12


def deg_in_sign(lon):
    return lon % 30


def nakshatra_of(lon):
    idx = int(lon // NAK_SPAN) % 27
    frac = (lon % NAK_SPAN) / NAK_SPAN
    pada = int((lon % NAK_SPAN) // (NAK_SPAN / 4)) + 1
    return {"index": idx, "name": NAKSHATRAS[idx], "lord": NAK_LORDS[idx],
            "fraction_elapsed": frac, "pada": pada}


def fmt_dms(lon):
    d = deg_in_sign(lon)
    return f"{SIGNS[sign_of(lon)]} {int(d)}°{int((d % 1) * 60):02d}'"


# --- varga (divisional chart) sign calculators --------------------------------
def navamsa_sign(lon):          # D9
    s, div = sign_of(lon), int(deg_in_sign(lon) // (30.0 / 9))
    return (s * 9 + div) % 12

def dashamsha_sign(lon):        # D10: odd from same sign, even from 9th
    s, div = sign_of(lon), int(deg_in_sign(lon) // 3.0)
    return (s + div) % 12 if s % 2 == 0 else (s + 8 + div) % 12

def saptamsha_sign(lon):        # D7: odd from same sign, even from 7th
    s, div = sign_of(lon), int(deg_in_sign(lon) // (30.0 / 7))
    return (s + div) % 12 if s % 2 == 0 else (s + 6 + div) % 12

def dwadashamsha_sign(lon):     # D12: from the sign itself
    s, div = sign_of(lon), int(deg_in_sign(lon) // 2.5)
    return (s + div) % 12

VARGA_FUNCS = {"D9": navamsa_sign, "D10": dashamsha_sign,
               "D7": saptamsha_sign, "D12": dwadashamsha_sign}


# --- dignity ------------------------------------------------------------------
def dignity_of(planet, lon):
    s, d = sign_of(lon), deg_in_sign(lon)
    if planet in EXALTATION and EXALTATION[planet][0] == s:
        return "exalted"
    if planet in DEBILITATION and DEBILITATION[planet][0] == s:
        return "debilitated"
    mt = MOOLATRIKONA.get(planet)
    if mt and mt[0] == s and mt[1] <= d <= mt[2]:
        return "moolatrikona"
    if s in OWN_SIGNS.get(planet, []):
        return "own sign"
    lord = SIGN_LORDS[s]
    rel = NATURAL_FRIENDS.get(planet, {"friends": [], "enemies": []})
    if lord in rel["friends"]:
        return "friend's sign"
    if lord in rel["enemies"]:
        return "enemy's sign"
    return "neutral sign"


# --- chart computation --------------------------------------------------------
class BirthData:
    def __init__(self, year, month, day, hour, minute, tz_offset_hours,
                 lat, lon, place="", second=0):
        self.year, self.month, self.day = year, month, day
        self.hour, self.minute, self.second = hour, minute, second
        self.tz = tz_offset_hours
        self.lat, self.lon, self.place = lat, lon, place

    @property
    def jd_ut(self):
        ut = self.hour + self.minute / 60.0 + self.second / 3600.0 - self.tz
        return swe.julday(self.year, self.month, self.day, ut)

    @property
    def local_dt(self):
        return dt.datetime(self.year, self.month, self.day, self.hour,
                           self.minute, int(self.second))

    def key(self):
        raw = f"{self.year}-{self.month}-{self.day}T{self.hour}:{self.minute}:{self.second}" \
              f"@{self.lat},{self.lon},tz{self.tz}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


def jd_to_datetime(jd):
    y, m, d, h = swe.revjul(jd)
    hh = int(h); mm = int((h - hh) * 60)
    return dt.datetime(y, m, d, hh, mm)


def compute_chart(birth: BirthData, node_type="true"):
    """Compute the full sidereal chart. Returns a plain dict (JSON-serialisable)."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = birth.jd_ut
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

    cusps, ascmc = swe.houses_ex(jd, birth.lat, birth.lon, b'W', swe.FLG_SIDEREAL)
    asc_lon = ascmc[0]
    asc_sign = sign_of(asc_lon)

    planets = {}
    sun_lon = None
    for name, pid in PLANET_IDS.items():
        pos, _ = swe.calc_ut(jd, pid, flags)
        planets[name] = {"lon": pos[0], "speed": pos[3]}
        if name == "Sun":
            sun_lon = pos[0]

    node_id = swe.TRUE_NODE if node_type == "true" else swe.MEAN_NODE
    npos, _ = swe.calc_ut(jd, node_id, flags)
    planets["Rahu"] = {"lon": npos[0], "speed": npos[3]}
    planets["Ketu"] = {"lon": (npos[0] + 180) % 360, "speed": npos[3]}

    out = {"meta": {"ayanamsha": "Lahiri", "ayanamsha_value": swe.get_ayanamsa_ut(jd),
                    "house_system": "Whole Sign", "node_type": node_type,
                    "jd_ut": jd, "engine": f"Swiss Ephemeris {swe.version}",
                    "birth": {"date": f"{birth.year:04d}-{birth.month:02d}-{birth.day:02d}",
                              "time_local": f"{birth.hour:02d}:{birth.minute:02d}",
                              "tz": birth.tz, "lat": birth.lat, "lon": birth.lon,
                              "place": birth.place}},
           "ascendant": {"lon": asc_lon, "sign": asc_sign, "sign_name": SIGNS[asc_sign],
                         "deg": deg_in_sign(asc_lon), "nakshatra": nakshatra_of(asc_lon),
                         "str": fmt_dms(asc_lon)},
           "planets": {}}

    for name in GRAHAS:
        p = planets[name]
        lon_, speed = p["lon"], p["speed"]
        s = sign_of(lon_)
        house = ((s - asc_sign) % 12) + 1
        entry = {"lon": lon_, "sign": s, "sign_name": SIGNS[s],
                 "deg": deg_in_sign(lon_), "house": house, "str": fmt_dms(lon_),
                 "nakshatra": nakshatra_of(lon_),
                 "retrograde": bool(speed < 0) if name not in ("Sun", "Moon") else False,
                 "dignity": dignity_of(name, lon_)}
        # nodes are always retrograde in true-node mode by convention
        if name in ("Rahu", "Ketu"):
            entry["retrograde"] = True
        # combustion
        if name in COMBUSTION_ORB:
            orb = COMBUSTION_ORB_RETRO.get(name) if entry["retrograde"] and name in COMBUSTION_ORB_RETRO else COMBUSTION_ORB[name]
            dist = abs((lon_ - sun_lon + 180) % 360 - 180)
            entry["combust"] = bool(dist <= orb)
            entry["sun_distance"] = round(dist, 2)
        # vargas
        entry["vargas"] = {v: {"sign": f(lon_), "sign_name": SIGNS[f(lon_)]}
                           for v, f in VARGA_FUNCS.items()}
        entry["vargottama"] = bool(entry["vargas"]["D9"]["sign"] == s)
        out["planets"][name] = entry

    # varga ascendants
    out["varga_lagnas"] = {v: {"sign": f(asc_lon), "sign_name": SIGNS[f(asc_lon)]}
                           for v, f in VARGA_FUNCS.items()}

    # whole-sign house table
    out["houses"] = {}
    for h in range(1, 13):
        s = (asc_sign + h - 1) % 12
        occupants = [n for n in GRAHAS if out["planets"][n]["sign"] == s]
        lord = SIGN_LORDS[s]
        out["houses"][str(h)] = {"sign": s, "sign_name": SIGNS[s], "lord": lord,
                                 "lord_house": out["planets"][lord]["house"],
                                 "occupants": occupants}

    # birth-time sensitivity: does the ascendant sign hold at ±5 minutes?
    stable = True
    for dmin in (-5, 5):
        jd2 = jd + dmin / (24 * 60.0)
        _, a2 = swe.houses_ex(jd2, birth.lat, birth.lon, b'W', swe.FLG_SIDEREAL)
        if sign_of(a2[0]) != asc_sign:
            stable = False
    out["meta"]["asc_stable_pm5min"] = stable
    return out


# --- chart store (compute once per birth data) --------------------------------
STORE_DIR = os.path.join(os.path.dirname(EPHE_PATH), "charts")

def get_chart(birth: BirthData, node_type="true", force=False):
    os.makedirs(STORE_DIR, exist_ok=True)
    path = os.path.join(STORE_DIR, f"{birth.key()}_{node_type}.json")
    if os.path.exists(path) and not force:
        with open(path) as f:
            return json.load(f)
    chart = compute_chart(birth, node_type)
    with open(path, "w") as f:
        json.dump(chart, f, indent=1)
    return chart
