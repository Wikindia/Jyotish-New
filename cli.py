"""
CLI. Examples:

  # full chart
  python -m jyotish.cli chart --date 1999-06-13 --time 13:33 --tz 5.5 \
      --lat 25.2138 --lon 75.8648 --place "Kota"

  # ask a question
  python -m jyotish.cli ask --date 1999-06-13 --time 13:33 --tz 5.5 \
      --lat 25.2138 --lon 75.8648 "when will I get married"

  # dashas / varshaphal
  python -m jyotish.cli dasha --system vimshottari ...
  python -m jyotish.cli varsha --year 2026 ...
"""
import argparse
import json
import datetime as dt
from .core import BirthData, get_chart, SIGNS, fmt_dms
from .dashas import (vimshottari, chara_dasha, narayana_dasha, varshaphal,
                     ashtottari, ASHTAMANGALA_NOTE)
from .yogas import detect_yogas
from .qa import answer, render


def _birth(args):
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm = (int(x) for x in args.time.split(":"))
    return BirthData(y, m, d, hh, mm, args.tz, args.lat, args.lon,
                     place=args.place or "")


def print_chart(chart):
    m = chart["meta"]
    print(f"Birth: {m['birth']['date']} {m['birth']['time_local']} "
          f"(UTC{m['birth']['tz']:+.1f})  {m['birth']['place']}")
    print(f"Engine: {m['engine']} | {m['ayanamsha']} ayanamsha "
          f"({m['ayanamsha_value']:.4f}°) | {m['house_system']} | {m['node_type']} node\n")
    a = chart["ascendant"]
    print(f"{'Ascendant':10s} {a['str']:22s} {a['nakshatra']['name']}")
    for g, p in chart["planets"].items():
        flags = []
        if p["retrograde"] and g not in ("Rahu", "Ketu"):
            flags.append("R")
        if p.get("combust"):
            flags.append("combust")
        if p["vargottama"]:
            flags.append("vargottama")
        if p["dignity"] in ("exalted", "debilitated"):
            flags.append(p["dignity"])
        print(f"{g:10s} {p['str']:16s} H{p['house']:<3d} {p['nakshatra']['name']:18s}"
              f" {p['nakshatra']['pada']}p  {' '.join(flags)}")
    if not m["asc_stable_pm5min"]:
        print("\n⚠ Ascendant sign is sensitive to ±5 min of birth time.")
    print("\nYogas present:")
    for y in detect_yogas(chart):
        print(f"  • {y['yoga']} — {y['evidence']}")


def main():
    p = argparse.ArgumentParser(prog="jyotish")
    p.add_argument("command", choices=["chart", "ask", "dasha", "varsha"])
    p.add_argument("question", nargs="*", default=[])
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--time", required=True, help="HH:MM local")
    p.add_argument("--tz", type=float, default=5.5, help="UTC offset hours (IST=5.5)")
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--place", default="")
    p.add_argument("--node", choices=["true", "mean"], default="true")
    p.add_argument("--system", default="vimshottari",
                   choices=["vimshottari", "chara", "narayana", "ashtottari"])
    p.add_argument("--year", type=int, default=dt.date.today().year)
    p.add_argument("--horizon", type=float, default=5, help="years ahead for 'ask'")
    p.add_argument("--json", action="store_true")
    args = p.parse_intermixed_args()

    chart = get_chart(_birth(args), node_type=args.node)

    if args.command == "chart":
        print_chart(chart)

    elif args.command == "ask":
        q = " ".join(args.question)
        if not q:
            raise SystemExit("Provide a question, e.g.:  ask ... \"when will I get married\"")
        rep = answer(chart, q, horizon_years=args.horizon)
        print(json.dumps(rep, indent=1, default=str) if args.json else render(rep))

    elif args.command == "dasha":
        fn = {"vimshottari": lambda: vimshottari(chart, levels=2),
              "chara": lambda: chara_dasha(chart, cycles=2),
              "narayana": lambda: narayana_dasha(chart, cycles=2),
              "ashtottari": lambda: ashtottari(chart)}[args.system]
        d = fn()
        print(d["system"])
        if args.system == "ashtottari":
            print(("APPLICABLE" if d["classically_applicable"] else "NOT classically applicable")
                  + f" — rule: {d['applicability_rule']}")
            print(ASHTAMANGALA_NOTE + "\n")
        for t in d["timeline"]:
            label = t.get("lord") or t.get("sign_name")
            extra = f" ({t['years']}y, lord {t['lord_used']})" if "years" in t else ""
            print(f"  {t['start']} → {t['end']}  {label}{extra}")

    elif args.command == "varsha":
        v = varshaphal(chart, args.year)
        print(f"{v['system']} {v['year']} — solar return {v['solar_return_utc']}")
        va = v["varsha_chart"]["ascendant"]
        print(f"Varsha lagna: {va['str']} | Muntha: {v['muntha']['sign_name']} "
              f"(H{v['muntha']['house_from_varsha_lagna']} from varsha lagna)")
        print("Mudda dasha:")
        for mmd in v["mudda_dasha"]:
            print(f"  {mmd['start']} → {mmd['end']}  {mmd['lord']}")
        print(f"\n{v['note']}")


if __name__ == "__main__":
    main()
