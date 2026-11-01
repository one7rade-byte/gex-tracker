"""
validate_dashboard_signal.py — daily post-pull sanity checks for gex-tracker.

Runs in gex_daily.yml right after regime_analyzer.py and before the CSV
commit. The workflow step uses continue-on-error, so a finding here can
never block the actual data pull.

Checks (latest row only — historical rows are not re-judged):
  1. Today's saved net_gex_b (and qqq_gex_b) is within GEX_SANITY_CAP_B.
     Guards against a repeat of the 2026-10-30 bad parse (-147.8B).
  2. gex_log.csv `signal` and regime_log.csv `regime_signal` for the same
     date don't flatly contradict each other (BUY vs EXIT/DEFENSIVE/CRISIS).
     Under the v2 compute_signal logic, RED EXIT needs RSI >= 57 while
     regime BUY_WATCH/STRONG_BUY need RSI < 57/50, so a same-day clash
     means something upstream is broken, not a normal disagreement.
     (Four pre-v2 rows from Jun/Jul 2026 do clash — expected, not re-checked.)
  3. index.html has no computeSignal(...) call with a bare [] argument or
     fewer than 4 arguments — the exact pattern behind the Oct-30 bug where
     a real STRONG_BUY day displayed as "Hold" in the Full History table.

On any finding: sends one Telegram alert (separate from the daily summary)
and exits 1. On a clean run: prints "Validation passed", stays silent on
Telegram, exits 0.
"""

import csv
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
GEX_LOG = os.path.join(ROOT, "gex_log.csv")
REGIME_LOG = os.path.join(ROOT, "regime_log.csv")
INDEX_HTML = os.path.join(ROOT, "index.html")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DEFAULT_CAP_B = 60.0


def load_sanity_cap():
    """Read GEX_SANITY_CAP_B from gex_tracker.py so the two can't drift apart.
    Parsed as text rather than imported, so nothing in gex_tracker runs."""
    try:
        with open(os.path.join(ROOT, "gex_tracker.py"), encoding="utf-8") as f:
            m = re.search(r"^GEX_SANITY_CAP_B\s*=\s*([0-9.]+)", f.read(), re.M)
        if m:
            return float(m.group(1))
    except OSError:
        pass
    return DEFAULT_CAP_B


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Check 1: GEX within sanity bound ─────────────────────────────────────────
def check_gex_bound(latest, cap):
    findings = []
    for col in ("net_gex_b", "qqq_gex_b"):
        raw = (latest.get(col) or "").strip()
        if raw == "":
            # Blank is the intended outcome when gex_tracker rejects a bad
            # parse — log it, but it isn't a validation failure by itself.
            print(f"  note: {col} blank for {latest.get('date')} (parse rejected or unavailable)")
            continue
        val = to_float(raw)
        if val is None:
            findings.append(f"{col}={raw!r} on {latest.get('date')} is not a number")
        elif abs(val) > cap:
            findings.append(
                f"{col}={val}B on {latest.get('date')} exceeds the ±{cap:g}B sanity cap"
            )
    return findings


# ── Check 2: gex signal vs regime signal ─────────────────────────────────────
def classify_gex_signal(s):
    u = (s or "").upper()
    if "BUY" in u:
        return "BUY"
    if "EXIT" in u:
        return "EXIT"
    return "OTHER"


def classify_regime_signal(s):
    u = (s or "").upper().strip()
    if u in ("STRONG_BUY", "BUY_WATCH"):
        return "BUY"
    if u in ("DEFENSIVE", "CRISIS"):
        return "EXIT"
    return "OTHER"


def check_signal_agreement(latest, regime_rows):
    date = latest.get("date")
    match = [r for r in regime_rows if r.get("date") == date]
    if not match:
        return [f"regime_log.csv has no row for {date} (gex_log.csv does)"]
    reg = match[-1].get("regime_signal", "")
    g_cls = classify_gex_signal(latest.get("signal"))
    r_cls = classify_regime_signal(reg)
    if {g_cls, r_cls} == {"BUY", "EXIT"}:
        return [
            f"Signal contradiction on {date}: gex_log signal "
            f"'{(latest.get('signal') or '')[:60]}' vs regime_signal '{reg}'"
        ]
    return []


# ── Check 3: no under-specified computeSignal calls in index.html ────────────
def split_top_level_args(argstr):
    """Split a call's argument string on top-level commas only."""
    args, depth, cur, quote = [], 0, [], None
    for ch in argstr:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        args.append(tail)
    return args


def check_index_html():
    findings = []
    try:
        with open(INDEX_HTML, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return [f"could not read index.html: {e}"]

    for m in re.finditer(r"computeSignal\s*\(", text):
        # Skip the function definition itself.
        before = text[max(0, m.start() - 20):m.start()]
        if re.search(r"function\s+$", before):
            continue
        # Walk to the matching close paren.
        i, depth = m.end(), 1
        while i < len(text) and depth:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        argstr = text[m.end():i - 1]
        args = split_top_level_args(argstr)
        line = text.count("\n", 0, m.start()) + 1
        if any(a == "[]" for a in args):
            findings.append(f"index.html:{line} computeSignal call passes a bare [] ({argstr[:60]})")
        elif len(args) < 4:
            findings.append(
                f"index.html:{line} computeSignal call has only {len(args)} args "
                f"(rsi etc. would silently default) ({argstr[:60]})"
            )
    return findings


# ── Alerting ─────────────────────────────────────────────────────────────────
def send_alert(findings):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set — alert not sent)")
        return
    text = "⚠️ GEX tracker validation found a problem:\n\n" + "\n".join(
        f"• {f}" for f in findings
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]},
            timeout=15,
        )
        print(f"  Telegram alert status: {r.status_code}")
    except requests.RequestException as e:
        print(f"  Telegram alert failed: {e}")


def main():
    gex_rows = read_rows(GEX_LOG)
    regime_rows = read_rows(REGIME_LOG)
    if not gex_rows:
        findings = ["gex_log.csv is empty"]
    else:
        latest = gex_rows[-1]
        print(f"Validating latest gex_log row: {latest.get('date')}")
        findings = []
        findings += check_gex_bound(latest, load_sanity_cap())
        findings += check_signal_agreement(latest, regime_rows)
    findings += check_index_html()

    if findings:
        print("Validation FAILED:")
        for f in findings:
            print(f"  - {f}")
        send_alert(findings)
        sys.exit(1)
    print("Validation passed")


if __name__ == "__main__":
    main()
