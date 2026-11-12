#!/usr/bin/env python3
"""Render a VARIABLE cold-call HTML body for Zayo Visuals.

Past sent emails are INSPIRATION ONLY (concepts: personalized hook ->
observation about thumbnails -> what I do + portfolio -> low-friction CTA).
They are NOT a fixed template. Each lead gets a hook variant chosen by a
stable hash of the channel name (same lead -> same variant, different
leads -> different variants). When nicho is unknown, a no-niche variant
is used so the message never repeats itself (e.g. never
"procurando sobre seus vídeos e dei uma olhada nos seus vídeos").

Rules baked in (user-mandated):
- NEVER mention free sample/model in the 1st email.
- Portfolio link ALWAYS inline, MASKED: "Zayo Visuals - Portfólio/Portfolio".
- Subject stays fixed; body varies.
- Signature IMAGE is appended automatically by google_api.py --sig-img.

Usage:
  render_cold_email.py --name "FUT 442" --nicho "Futebol" --lang pt > body.html
  render_cold_email.py --name "miniBronze" --nicho "Overwatch" --lang en > body.html
"""
import argparse
import hashlib

PORT = "https://www.behance.net/zayovisuals"
CSS = ("font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
       "font-size:15px;line-height:1.6;color:#222222;")
LINK_STYLE = "color:#0066cc;text-decoration:underline;font-weight:500;"

SUBJECTS = {"pt": "Uma observação sobre suas thumbnails",
            "en": "A quick thought about your thumbnails"}

GREETINGS = {
    "pt": ["Fala, {nome}! Tudo certo?", "E aí, {nome}, beleza?", "Oi, {nome}! Tudo bem por aí?"],
    "en": ["Hey {nome}! How's it going?", "Hi {nome}! Hope you're doing well.", "Hey {nome}, what's up?"],
}

# Hooks WITH niche (nicho mentioned once, naturally)
HOOKS_NICHE = {
    "pt": [
        "Conheci seu canal procurando sobre {nicho} e conferi alguns vídeos — curti demais a proposta. Só senti que as thumbnails ainda não estão transmitindo toda a energia do conteúdo no feed.",
        "Encontrei seus vídeos sobre {nicho} esses dias e gostei do que vi. Reparei que dá pra deixar as thumbs com mais contraste e hierarquia visual pra chamar mais atenção.",
        "Tava procurando conteúdo de {nicho} e seu canal apareceu — parei pra ver alguns vídeos e curti. Uma coisa me chamou atenção: as thumbnails podem ganhar mais impacto pra subir o CTR.",
        "Vi alguns vídeos seus sobre {nicho} e o conteúdo tá massa. Só achei que as thumbs não acompanham tanto a qualidade do vídeo.",
    ],
    "en": [
        "I came across your channel while looking for {nicho} content and watched a few videos — really liked the vibe. I just felt the thumbnails could pop more on the home feed.",
        "Found your {nicho} videos the other day and enjoyed them. One thing stood out: the thumbs could use bolder contrast and a clearer visual hierarchy to boost CTR.",
        "Was searching for {nicho} creators and your channel showed up — checked a few videos and liked what I saw. The thumbnails, though, could use more impact.",
        "Watched some of your {nicho} content recently — solid stuff. I noticed the thumbs don't quite match the quality of the videos yet.",
    ],
}

# Hooks WITHOUT niche (must NOT repeat the word "vídeos/videos" twice)
HOOKS_NO_NICHE = {
    "pt": [
        "Seu canal apareceu pra mim esses dias e resolvi dar uma olhada — curti a proposta. Notei uma coisa nas suas thumbnails que creo que dá pra explorar melhor.",
        "Achei seu canal navegando pelo YouTube e conferi seu conteúdo — gostei do que vi. Só senti falta de mais impacto visual nas thumbs.",
        "Vi seu canal essa semana e parei pra acompanhar — tá bem legal. Uma coisa me chamou atenção: dá pra deixar as thumbnails mais fortes no feed.",
        "Descobri seu canal recentemente e olhei com calma — curti demais. Reparei que as thumbs podem ganhar mais destaque visual.",
    ],
    "en": [
        "Your channel showed up for me recently and I checked it out — liked the vibe. One thing I noticed: the thumbnails could stand out more on the feed.",
        "Came across your channel while browsing YouTube and gave it a look — nice content. The thumbnails, though, could use a bit more punch.",
        "Found your channel this week and watched a bit — good stuff. Something stood out to me: the thumbs could grab more attention.",
        "Discovered your channel recently and checked out your content — enjoyed it. I did notice the thumbnails could be stronger visually.",
    ],
}

BRIDGE = {
    "pt": "Trabalho com thumbnails para YouTube. Se quiser dar uma olhada no meu portfólio:<br>\n  {link}",
    "en": "I design YouTube thumbnails. If you want to take a look at my portfolio:<br>\n  {link}",
}
CTA = {
    "pt": ["Se tiver interesse, é só chamar — sem compromisso.", "Caso queira conversar, fico à disposição.", "Se fizer sentido pra você, podemos trocar uma ideia."],
    "en": ["If you're open to it, happy to chat — no pressure at all!", "If it makes sense for you, we could talk.", "If you're interested, just let me know."],
}
SIGNOFF = {"pt": "Abraço,", "en": "Best regards,"}


def pick(options, name, salt=""):
    h = int(hashlib.md5((name + salt).encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def render(name, nicho, lang):
    nicho = (nicho or "").strip()
    pool = HOOKS_NICHE[lang] if nicho else HOOKS_NO_NICHE[lang]
    hook = pick(pool, name, "hook").format(nicho=nicho.lower() or nicho)
    greeting = pick(GREETINGS[lang], name, "greet").format(nome=name)
    cta = pick(CTA[lang], name, "cta")
    link_txt = "Zayo Visuals - Portfólio" if lang == "pt" else "Zayo Visuals - Portfolio"
    link = f'👉 <a href="{PORT}" style="{LINK_STYLE}">{link_txt}</a>'
    bridge = BRIDGE[lang].format(link=link)
    return (
        f'<div style="{CSS}">\n'
        f'  <p>{greeting}</p>\n'
        f'  <p>{hook}</p>\n'
        f'  <p>{bridge}</p>\n'
        f'  <p>{cta}</p>\n'
        f'  <p>{SIGNOFF[lang]}</p>\n'
        f'</div>\n'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="channel name as shown on YouTube")
    ap.add_argument("--nicho", default="", help="niche (may be empty)")
    ap.add_argument("--lang", choices=["pt", "en"], required=True)
    ap.add_argument("--subject", action="store_true", help="print only the subject line")
    args = ap.parse_args()
    if args.subject:
        print(SUBJECTS[args.lang])
    else:
        print(render(args.name, args.nicho, args.lang), end="")


if __name__ == "__main__":
    main()
