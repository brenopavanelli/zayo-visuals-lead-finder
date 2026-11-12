#!/usr/bin/env python3
"""Layered contact extraction for leadfinder channels (Zayo Visuals).

Usage:
  python3 scripts/extract_contacts.py src/output/leads.csv output/contacts.json

Layers (cheapest first):
  1. YouTube Data API channels.list part=snippet (batch of 50, 1 quota unit) -> description
  2. GET youtube.com/channel/<UCID>/about  -> regex HTML
  3. /channel/<UCID>/videos -> 2 most recent videoIds -> /watch?v=.. -> regex descriptions
  4. DuckDuckGo HTML search fallback: '"<channel name>" youtube contato email instagram discord'

Every found contact is VALIDATED against the channel name (domain/handle must
match; well-known foreign brand domains only if the channel name contains the
brand). Invalid -> discarded with reason. Progress is persisted every 10 items
(output/contacts_progress.json) so a timeout never loses the batch.

Output JSON: [{channel fields..., channel_id, contact, src} | {.., contact:"", src:"none", reason:...}]
"""
import csv
import difflib
import io
import json
import os
import re
import sys
import time

import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(REPO, ".env")
OUT_DIR = os.path.join(REPO, "output")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
BAD_DOMAINS = ("youtube.com", "google.com", "sentry.io", "schema.org", "w3.org",
               "g.co", "youtu.be", "apify.com", "cleantalk.org", "wikipedia.org",
               "play.google.com", "apps.apple.com", "duckduckgo.com", "bing.com",
               "yahoo.com", "example.com", "email.com")
FOREIGN_BRANDS = ["mkbhd.com", "thegamingsetup.com", "livecounts.nl", "fixated.com",
                  "vidiq.com", "tubebuddy.com", "socialblade.com", "famousbirthdays.com",
                  "linkedin.com", "facebook.com", "linktr.ee", "beacons.ai"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"}


def api_key():
    for line in open(ENV):
        if line.startswith("YOUTUBE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("YOUTUBE_API_KEY missing in .env")


def find_contacts(text):
    emails = [e for e in dict.fromkeys(EMAIL_RE.findall(text))
              if not any(b in e.lower() for b in BAD_DOMAINS)]
    ig = sorted(set(re.findall(r"https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.\-]+/?", text)))
    dc = sorted(set(re.findall(r"https?://(?:www\.)?(?:discord\.gg|discord\.com/invite)/[a-zA-Z0-9_\-]+", text)))
    tw = sorted(set(re.findall(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+", text)))
    tk = sorted(set(re.findall(r"https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.\-]+", text)))
    for lst, name in [(emails, "email"), (ig, "instagram"), (dc, "discord"), (tw, "twitter"), (tk, "tiktok")]:
        if lst:
            return lst[0], name
    return "", ""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def validate(contact, channel_name):
    """Return None if valid, else a reason string."""
    c = contact.lower()
    name = norm(channel_name)
    for d in FOREIGN_BRANDS:
        if d in c:
            brand = d.split(".")[0]
            if brand not in name:
                return f"foreign-brand domain ({brand}) != channel name"
    m = re.search(r"(?:instagram\.com|tiktok\.com/@|twitter\.com|x\.com)/([a-zA-Z0-9_.\-]+)", c)
    if m:
        h = norm(m.group(1))
        if h and name and difflib.SequenceMatcher(None, h, name).ratio() < 0.45 \
                and h not in name and name not in h:
            return f"social handle '{m.group(1)}' != channel name"
    return None


def layer_api_descriptions(ids):
    key = api_key()
    descs = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "snippet", "id": ",".join(batch), "key": key}, timeout=30)
        for it in r.json().get("items", []):
            descs[it["id"]] = it["snippet"].get("description", "")
        time.sleep(0.2)
    return descs


def scrape_about(cid):
    try:
        r = requests.get(f"https://www.youtube.com/channel/{cid}/about", headers=UA, timeout=12)
        return find_contacts(r.text)
    except Exception:
        return "", ""


def scrape_videos(cid):
    try:
        r = requests.get(f"https://www.youtube.com/channel/{cid}/videos", headers=UA, timeout=12)
        vids = list(dict.fromkeys(re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)))[:2]
        for vid in vids:
            try:
                rv = requests.get(f"https://www.youtube.com/watch?v={vid}", headers=UA, timeout=12)
                c, src = find_contacts(rv.text)
                if c:
                    return c, src
            except Exception:
                pass
            time.sleep(0.4)
    except Exception:
        pass
    return "", ""


def scrape_web_search(name):
    try:
        r = requests.post("https://html.duckduckgo.com/html/",
                          data={"q": f'"{name}" youtube contato email instagram discord'},
                          headers=UA, timeout=15)
        return find_contacts(r.text)
    except Exception:
        return "", ""


def main():
    leads_csv, out_json = sys.argv[1], sys.argv[2]
    os.makedirs(OUT_DIR, exist_ok=True)
    prog_path = os.path.join(OUT_DIR, "contacts_progress.json")
    progress = json.load(open(prog_path)) if os.path.exists(prog_path) else {}

    leads = list(csv.DictReader(open(leads_csv, encoding="utf-8-sig")))
    for l in leads:
        l["channel_id"] = l["channel_url"].split("/")[-1]

    todo = [l for l in leads if l["channel_id"] not in progress]
    print(f"leads: {len(leads)} | a processar: {len(todo)}")

    # layer 1: API descriptions for everyone
    descs = layer_api_descriptions([l["channel_id"] for l in leads])

    for i, l in enumerate(todo, 1):
        cid, name = l["channel_id"], l["channel_name"]
        contact, src = "", "none"
        c, s = find_contacts(descs.get(cid, ""))
        if c and not validate(c, name):
            contact, src = c, f"api:{s}"
        if not contact:
            time.sleep(0.4)
            c, s = scrape_about(cid)
            if c and not validate(c, name):
                contact, src = c, f"about:{s}"
        if not contact:
            time.sleep(0.4)
            c, s = scrape_videos(cid)
            if c and not validate(c, name):
                contact, src = c, f"video:{s}"
        if not contact:
            time.sleep(0.6)
            c, s = scrape_web_search(name)
            if c and not validate(c, name):
                contact, src = c, f"web:{s}"
        reason = "" if contact else (validate(c, name) if c else "no public contact found")
        progress[cid] = {"contact": contact, "src": src, "reason": reason}
        if i % 10 == 0:
            json.dump(progress, open(prog_path, "w"))
            print(f"[{i}/{len(todo)}] com contato até agora: "
                  f"{sum(1 for v in progress.values() if v['contact'])}")
        time.sleep(0.3)

    json.dump(progress, open(prog_path, "w"))
    out = []
    for l in leads:
        p = progress[l["channel_id"]]
        out.append({**l, "contact": p["contact"], "src": p["src"], "reason": p.get("reason", "")})
    json.dump(out, open(out_json, "w"), ensure_ascii=False, indent=1)
    ok = [o for o in out if o["contact"]]
    print(f"FINAL: {len(ok)}/{len(out)} com contato válido -> {out_json}")


if __name__ == "__main__":
    main()
