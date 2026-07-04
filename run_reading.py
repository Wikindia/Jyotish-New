"""
run_reading.py — GitHub Actions entry point.

Reads birth.json + question.txt, verifies the engine against the reference
chart, computes the deterministic report, has Claude narrate it (model reads
ONLY the verified chart JSON), and writes:
  LATEST_READING.md            (always the newest reading)
  readings/YYYY-MM-DD_HHMM.md  (permanent archive)
"""
import json
import os
import sys
import datetime as dt
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyotish.core import BirthData, get_chart
from jyotish.qa import answer, render

SYSTEM = """You are an experienced professional Jyotishi writing a reading.
Hard rules:
- Use ONLY the placements, dashas, windows, and yogas in the provided JSON.
  Never invent a placement, yoga, or dasha period. If the data doesn't support
  an answer, say so.
- Cite the specific placements/dashas driving every conclusion.
- Where the JSON shows convergence across systems, state it explicitly.
  Where systems disagree, say so — do not cherry-pick.
- Phrase outcomes as tendency/probability, never certainty.
- Direct, plain-spoken register. No horoscope-app filler.
- If asc_caution is present, state the birth-time caveat up front.
- Format the answer in clean Markdown with a short title."""


def narrate(question, chart, report, key):
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2500,
        "system": SYSTEM,
        "messages": [{"role": "user", "content":
                      f"Question: {question}\n\nVerified chart + computed report:\n"
                      f"{json.dumps({'chart': chart, 'report': report}, default=str)}"}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data["content"])


def main():
    with open("birth.json") as f:
        b = json.load(f)
    with open("question.txt") as f:
        question = f.read().strip()
    if not question:
        print("question.txt is empty — nothing to do.")
        return

    y, m, d = (int(x) for x in b["date"].split("-"))
    hh, mm = (int(x) for x in b["time"].split(":"))
    birth = BirthData(y, m, d, hh, mm, b["tz"], b["lat"], b["lon"], b.get("place", ""))
    chart = get_chart(birth)
    report = answer(chart, question, horizon_years=5)
    raw = render(report)

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        try:
            body = narrate(question, chart, report, key)
        except Exception as e:
            body = (f"*(AI narration failed: {e} — deterministic report below.)*\n\n"
                    f"```\n{raw}\n```")
    else:
        body = (f"*(No ANTHROPIC_API_KEY secret set — deterministic report below.)*\n\n"
                f"```\n{raw}\n```")

    now = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)  # IST
    stamp = now.strftime("%Y-%m-%d %H:%M IST")
    doc = (f"# Reading — {stamp}\n\n**Question:** {question}\n\n---\n\n{body}\n\n---\n"
           f"<details><summary>Deterministic engine output (audit trail)</summary>\n\n"
           f"```\n{raw}\n```\n</details>\n")

    with open("LATEST_READING.md", "w") as f:
        f.write(doc)
    os.makedirs("readings", exist_ok=True)
    with open(f"readings/{now.strftime('%Y-%m-%d_%H%M')}.md", "w") as f:
        f.write(doc)
    print(f"Reading written for: {question}")


if __name__ == "__main__":
    main()
