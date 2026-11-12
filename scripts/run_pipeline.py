#!/usr/bin/env python3
"""Autonomous Zayo Visuals outreach pipeline — one command runs everything.

  python3 scripts/run_pipeline.py                 # full run: fetch if empty + send up to 20
  python3 scripts/run_pipeline.py --dry-run       # render/select only, no sends, no writes
  python3 scripts/run_pipeline.py --max-send 5    # cap this run's sends
  python3 scripts/run_pipeline.py --no-fetch      # never run the leadfinder

Steps:
  1. Read planilha 'Leads - Youtube' (personal token, Sheets API).
  2. Pending contactable leads = rows with a valid EMAIL and 'Mensagem enviada?' != Sim.
     (Configured contact channels TODAY: email only. Social-only contacts are skipped.)
  3. If there are NO pending contactable leads -> run leadfinder (src/main.py),
     extract contacts (scripts/extract_contacts.py, layered+validated), dedupe by
     channel_url, append only contactable leads to the planilha.
  4. Select up to --max-send pending leads (highest score first).
  5. For each: render variable body (scripts/render_cold_email.py; BR->pt, else->en),
     send from zayovisuals@gmail.com via google_api_zayo.py --html --sig-img,
     then mark planilha 'Mensagem enviada?'=Sim + date.
  6. Append run log to the campaign note in the caderno (Drive).
  7. Print a JSON summary (this is what gets reported to the user):
     {fetched_new_leads, leads_found, leads_added, discarded, contacted,
      niches_contacted, languages, message_ids, errors}
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload
import io

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET_ID = "1Y2sDydleCEVMUjbMhXtqDyNOian6i3cunEx5xlk2zGI"
CADORNO_FOLDER = "1rnBdsgsZr9yUVwaIbEsVPXI684_MUyjM"  # 02_PROJETOS/P02_Agencia_Design_USD
LOG_NAME = "Zayo Visuals - Log de Campanhas.md"
WRAPPER = "/home/ubuntu/.hermes/skills/productivity/google-workspace/scripts/google_api_zayo.py"
SIG = os.path.join(REPO, "templates", "assinatura_email.png")
PERSONAL_TOKEN = os.path.expanduser("~/.hermes/google_token.json")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
EMAIL_CAP = 20


def gservice(name, version, token_path=PERSONAL_TOKEN):
    tok = json.load(open(token_path))
    creds = Credentials.from_authorized_user_info(tok)
    return build(name, version, credentials=creds)


def read_sheet(sheets):
    vals = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="A1:P500").execute()["values"]
    rows = []
    for i, r in enumerate(vals[1:], start=2):
        r += [""] * (15 - len(r))
        rows.append({"row": i, "name": r[0], "url": r[1], "country": r[2].strip().upper(),
                     "subs": r[3], "score": r[7], "nicho": r[8], "contact": r[9].strip(),
                     "sent": r[10].strip().lower()})
    return rows


def is_email(c):
    return bool(EMAIL_RE.match(c))


def run_leadfinder():
    print(">> leadfinder: rodando busca completa...")
    p = subprocess.run(["python3", "main.py"], cwd=os.path.join(REPO, "src"),
                       capture_output=True, text=True, timeout=540)
    if p.returncode != 0:
        raise RuntimeError(f"leadfinder falhou: {p.stderr[-300:]}")
    csv_path = os.path.join(REPO, "src", "output", "leads.csv")
    print(">> leadfinder: extraindo contatos (em camadas)...")
    out_json = os.path.join(REPO, "output", "contacts.json")
    subprocess.run(["python3", os.path.join(REPO, "scripts", "extract_contacts.py"),
                    csv_path, out_json], check=True, timeout=1500)
    return json.load(open(out_json))


def append_leads_to_sheet(sheets, contacts, existing_urls):
    new = [c for c in contacts if c["contact"] and is_email(c["contact"])
           and c["channel_url"] not in existing_urls]
    new.sort(key=lambda c: -int(c["score"]) if c["score"].isdigit() else 0)
    if not new:
        return 0, len(contacts) - len(new)

    def guess_nicho(name):
        n = name.lower()
        for k, v in {"fut": "Futebol", "fc": "Futebol", "carro": "Carros", "auto": "Carros",
                     "game": "Games", "gamer": "Games", "podcast": "Podcast", "nerd": "Nerd/Geek",
                     "anime": "Anime", "fortnite": "Fortnite", "minecraft": "Minecraft",
                     "valorant": "Valorant", "roblox": "Roblox"}.items():
            if k in n:
                return v
        return ""

    rows = [[c["channel_name"], c["channel_url"], c["country"], c["subscribers"],
             c["videos_found"], c["average_views"], c["last_video_date"], c["score"],
             guess_nicho(c["channel_name"]), c["contact"], "Não", "", "", "", ""] for c in new]
    for i in range(0, len(rows), 50):
        sheets.spreadsheets().values().append(
            spreadsheetId=SHEET_ID, range="A1", insertDataOption="INSERT_ROWS",
            valueInputOption="USER_ENTERED", body={"values": rows[i:i + 50]}).execute()
    # verify
    total = len(sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="A1:A600").execute()["values"])
    print(f">> planilha: {len(new)} leads adicionados (total agora {total} linhas)")
    return len(new), len(contacts) - len(new)


def render(name, nicho, lang):
    p = subprocess.run(["python3", os.path.join(REPO, "scripts", "render_cold_email.py"),
                        "--name", name, "--nicho", nicho or "", "--lang", lang],
                       capture_output=True, text=True, check=True)
    return p.stdout


def subject_for(lang):
    p = subprocess.run(["python3", os.path.join(REPO, "scripts", "render_cold_email.py"),
                        "--name", "x", "--nicho", "", "--lang", lang, "--subject"],
                       capture_output=True, text=True, check=True)
    return p.stdout.strip()


def send_one(r, lang, today, dry_run):
    body = render(r["name"], r["nicho"], lang)
    subj = subject_for(lang)
    tmp = f"/tmp/pipe_body_{r['row']}.html"
    open(tmp, "w", encoding="utf-8").write(body)
    if dry_run:
        return {"ok": True, "dry": True, "subject": subj, "body_preview": body[:200]}
    cmd = (f'python3 {WRAPPER} gmail send --to {r["contact"]!r} --subject {subj!r} '
           f'--from \'"Zayo Visuals" <zayovisuals@gmail.com>\' '
           f'--body "$(cat {tmp})" --html --sig-img {SIG}')
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    ok = '"status": "sent"' in p.stdout
    mid = None
    m = re.search(r'"id":\s*"([^"]+)"', p.stdout)
    if m:
        mid = m.group(1)
    return {"ok": ok, "msg_id": mid, "err": (p.stderr or p.stdout)[-200:] if not ok else ""}


def mark_sent(sheets, items, today):
    data = [{"range": f"K{x['row']}:L{x['row']}", "values": [["Sim", today]]}
            for x in items if x["ok"] and not x.get("dry")]
    if data:
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"valueInputOption": "USER_ENTERED", "data": data}).execute()


def log_caderno(drive, summary, today):
    q = f"name='{LOG_NAME}' and '{CADORNO_FOLDER}' in parents and trashed=false"
    files = drive.files().list(q=q, fields="files(id)").execute()["files"]
    lines = (f"\n## Rodada {today} — pipeline automático\n"
             f"- buscar leads novos: {'SIM' if summary['fetched_new_leads'] else 'não'} "
             f"(encontrados {summary['leads_found']}, adicionados {summary['leads_added']}, "
             f"descartados {summary['discarded']})\n"
             f"- contatados: {summary['contacted']} | idiomas: {summary['languages']} | "
             f"nichos: {summary['niches_contacted']}\n"
             f"- erros: {len(summary['errors'])}\n")
    if files:
        fid = files[0]["id"]
        req = drive.files().get_media(fileId=fid)
        buf = io.BytesIO(); d = MediaIoBaseDownload(buf, req); done = False
        while not done:
            _, done = d.next_chunk()
        content = buf.getvalue().decode("utf-8") + lines
        drive.files().update(fileId=fid, media_body=MediaInMemoryUpload(
            content.encode("utf-8"), mimetype="text/markdown")).execute()
    else:
        drive.files().create(body={"name": LOG_NAME, "parents": [CADORNO_FOLDER],
                                   "mimeType": "text/markdown"},
                             media_body=MediaInMemoryUpload(lines.encode("utf-8"),
                                                            mimetype="text/markdown"),
                             fields="id").execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-send", type=int, default=EMAIL_CAP)
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    today = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
    sheets = gservice("sheets", "v4")
    drive = gservice("drive", "v3")

    summary = {"date": today, "fetched_new_leads": False, "leads_found": 0,
               "leads_added": 0, "discarded": 0, "contacted": 0,
               "niches_contacted": {}, "languages": {}, "message_ids": [], "errors": []}

    rows = read_sheet(sheets)
    existing_urls = {r["url"] for r in rows if r["url"]}
    pending = [r for r in rows if r["contact"] and is_email(r["contact"])
               and r["sent"] not in ("sim", "yes", "enviado")]

    if not pending and not args.no_fetch:
        contacts = run_leadfinder()
        summary["fetched_new_leads"] = True
        summary["leads_found"] = len(contacts)
        added, discarded = append_leads_to_sheet(sheets, contacts, existing_urls)
        summary["leads_added"] = added
        summary["discarded"] = discarded
        rows = read_sheet(sheets)
        pending = [r for r in rows if r["contact"] and is_email(r["contact"])
                   and r["sent"] not in ("sim", "yes", "enviado")]

    pending.sort(key=lambda r: -int(r["score"]) if r["score"].isdigit() else 0)
    batch = pending[: args.max_send]
    print(f">> pendentes com email: {len(pending)} | enviando lote de {len(batch)} (cap {args.max_send})")

    niches, langs = Counter(), Counter()
    results = []
    for r in batch:
        lang = "pt" if r["country"] == "BR" else "en"
        res = send_one(r, lang, today, args.dry_run)
        res.update(row=r["row"], name=r["name"], contact=r["contact"], lang=lang,
                   nicho=r["nicho"] or "(sem nicho)")
        results.append(res)
        if res["ok"]:
            summary["contacted"] += 1
            niches[r["nicho"] or "(sem nicho)"] += 1
            langs[lang] += 1
            if res.get("msg_id"):
                summary["message_ids"].append(res["msg_id"])
        else:
            summary["errors"].append(f"{r['name']}: {res.get('err', '')}")
        print(f"  [{'OK' if res['ok'] else 'FALHOU'}{' dry' if res.get('dry') else ''}] "
              f"linha {r['row']} {lang} -> {r['contact'][:40]}")
        if not args.dry_run:
            time.sleep(2)

    if not args.dry_run:
        mark_sent(sheets, results, today)

    summary["niches_contacted"] = dict(niches)
    summary["languages"] = dict(langs)
    summary["dry_run"] = args.dry_run
    summary["pending_email_left"] = len(pending) - len(batch)

    if not args.dry_run:
        try:
            log_caderno(drive, summary, today)
        except Exception as e:
            summary["errors"].append(f"log caderno: {e}")

    print("\n===== RESUMO (JSON) =====")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
