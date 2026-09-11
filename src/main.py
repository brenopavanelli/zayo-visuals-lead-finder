import csv
import os

from datetime import datetime, timedelta, timezone

from youtube_api import (
    search_videos,
    get_channel_details,
    get_video_statistics
)

from filters import filter_channels
from scoring import calculate_score


# ============================================================
# CONFIGURAÇÕES
# ============================================================

KEYWORDS = [
    # Futebol
    "futebol",
    "futebol brasileiro",
    "notícias de futebol",
    "análise de futebol",
    "futebol europeu",
    "EA FC",

    # Carros
    "carros",
    "avaliação de carros",
    "carros usados",
    "preparação de carros",
    "modificação de carros",

    # Fitness / Academia
    "academia",
    "musculação",
    "bodybuilding",
    "treino",
    "transformação corporal",

    # Tecnologia
    "tecnologia",
    "review de tecnologia",
    "celulares",
    "computadores",
    "setup gamer",

    # Games
    "gameplay",
    "jogos",
    "jogos de PC",
    "jogos de PS5",
    "jogos de Xbox",

    # Anime
    "anime",
    "análise de anime",
    "review de anime",
    "notícias de anime",
    "ranking de anime",

]

# Quantos dias para trás pesquisar
DAYS = 30

# Quantas páginas por palavra-chave
#
# 2 páginas = até 100 resultados por keyword
MAX_PAGES = 2

# Resultados por página
MAX_RESULTS = 50

# Filtros de lead
MIN_SUBSCRIBERS = 1_000
MAX_SUBSCRIBERS = 20_000

# País do canal
#
# BR = Brasil
# None = qualquer país
COUNTRY = "BR"

# Se True:
# canais sem país informado serão excluídos.
REQUIRE_COUNTRY = True

# Arquivo de saída
OUTPUT_FILE = "output/leads.csv"


# ============================================================
# DATA DE CORTE
# ============================================================

now = datetime.now(timezone.utc)

published_after = (
    now - timedelta(days=DAYS)
).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# CABEÇALHO
# ============================================================

print()
print("=" * 70)
print("ZAYO VISUALS — YOUTUBE LEAD FINDER")
print("=" * 70)

print()
print(f"Palavras-chave: {len(KEYWORDS)}")
print(f"Período: últimos {DAYS} dias")
print(f"Páginas por keyword: {MAX_PAGES}")
print(
    f"Inscritos: "
    f"{MIN_SUBSCRIBERS:,} - {MAX_SUBSCRIBERS:,}"
)

if COUNTRY:
    print(f"País: {COUNTRY}")
else:
    print("País: qualquer")

print()
print("=" * 70)


# ============================================================
# 1. BUSCAR VÍDEOS
# ============================================================

all_videos = []

for keyword in KEYWORDS:

    print()
    print("-" * 70)
    print(f"BUSCANDO: {keyword}")
    print("-" * 70)

    try:

        videos = search_videos(
            query=keyword,
            published_after=published_after,
            max_pages=MAX_PAGES,
            max_results=MAX_RESULTS
        )

        all_videos.extend(videos)

        print(
            f"  Total: {len(videos)} vídeos"
        )

    except Exception as error:

        print(
            f"  ERRO: {error}"
        )


# ============================================================
# 2. REMOVER VÍDEOS DUPLICADOS
# ============================================================

unique_videos = {}

for video in all_videos:

    video_id = (
        video
        .get("id", {})
        .get("videoId")
    )

    if not video_id:
        continue

    unique_videos[video_id] = video


print()
print("=" * 70)
print("ETAPA 1 CONCLUÍDA")
print("=" * 70)

print(
    f"Vídeos encontrados: "
    f"{len(all_videos)}"
)

print(
    f"Vídeos únicos: "
    f"{len(unique_videos)}"
)


# ============================================================
# 3. IDENTIFICAR CANAIS
# ============================================================

channel_ids = set()

for video in unique_videos.values():

    channel_id = (
        video
        .get("snippet", {})
        .get("channelId")
    )

    if channel_id:
        channel_ids.add(channel_id)


channel_ids = list(channel_ids)


print()
print(
    f"Canais únicos encontrados: "
    f"{len(channel_ids)}"
)


# ============================================================
# 4. BUSCAR DADOS DOS CANAIS
# ============================================================

print()
print("=" * 70)
print("BUSCANDO DADOS DOS CANAIS")
print("=" * 70)

channels = get_channel_details(
    channel_ids
)

print(
    f"Canais retornados pela API: "
    f"{len(channels)}"
)


# ============================================================
# 5. FILTRAR CANAIS
# ============================================================

filtered_channels = filter_channels(
    channels=channels,
    min_subscribers=MIN_SUBSCRIBERS,
    max_subscribers=MAX_SUBSCRIBERS,
    country=COUNTRY,
    require_country=REQUIRE_COUNTRY
)


print()
print("=" * 70)
print("FILTROS")
print("=" * 70)

print(
    f"Canais antes dos filtros: "
    f"{len(channels)}"
)

print(
    f"Canais após os filtros: "
    f"{len(filtered_channels)}"
)


# ============================================================
# 6. PEGAR VÍDEOS DOS CANAIS FILTRADOS
# ============================================================

filtered_channel_ids = set(
    filtered_channels.keys()
)

filtered_video_ids = []

for video_id, video in unique_videos.items():

    channel_id = (
        video
        .get("snippet", {})
        .get("channelId")
    )

    if channel_id in filtered_channel_ids:
        filtered_video_ids.append(
            video_id
        )


print()
print("=" * 70)
print("BUSCANDO ESTATÍSTICAS DOS VÍDEOS")
print("=" * 70)

print(
    f"Vídeos para análise: "
    f"{len(filtered_video_ids)}"
)


video_statistics = get_video_statistics(
    filtered_video_ids
)


# ============================================================
# 7. MONTAR LEADS
# ============================================================

leads = []

for channel_id, channel in filtered_channels.items():

    channel_videos = []

    for video_id in filtered_video_ids:

        video = video_statistics.get(
            video_id
        )

        if not video:
            continue

        if video["channel_id"] != channel_id:
            continue

        channel_videos.append(video)

    if not channel_videos:
        continue

    # ========================================================
    # MÉTRICAS
    # ========================================================

    views = [
        video["views"]
        for video in channel_videos
    ]

    average_views = (
        sum(views) / len(views)
    )

    last_video_date = max(
        video["published_at"]
        for video in channel_videos
    )

    videos_found = len(
        channel_videos
    )

    score = calculate_score(
        average_views=average_views,
        subscribers=channel["subscribers"],
        videos_found=videos_found,
        last_video_date=last_video_date
    )

    leads.append({

        "channel_name":
            channel["channel_name"],

        "channel_url":
            f"https://www.youtube.com/channel/"
            f"{channel_id}",

        "country":
            channel["country"] or "",

        "subscribers":
            channel["subscribers"],

        "videos_found":
            videos_found,

        "average_views":
            round(average_views),

        "last_video_date":
            last_video_date,

        "score":
            score
    })


# ============================================================
# 8. ORDENAR POR SCORE
# ============================================================

leads.sort(
    key=lambda lead: (
        lead["score"],
        lead["average_views"]
    ),
    reverse=True
)


# ============================================================
# 9. CRIAR PASTA OUTPUT
# ============================================================

os.makedirs(
    "output",
    exist_ok=True
)


# ============================================================
# 10. EXPORTAR CSV
# ============================================================

fieldnames = [
    "channel_name",
    "channel_url",
    "country",
    "subscribers",
    "videos_found",
    "average_views",
    "last_video_date",
    "score"
]


with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8-sig"
) as csvfile:

    writer = csv.DictWriter(
        csvfile,
        fieldnames=fieldnames
    )

    writer.writeheader()

    writer.writerows(
        leads
    )


# ============================================================
# 11. RESULTADO FINAL
# ============================================================

print()
print("=" * 70)
print("RESULTADO FINAL")
print("=" * 70)

print()
print(
    f"LEADS ENCONTRADOS: {len(leads)}"
)

print()
print(
    f"CSV criado em:"
)

print(
    f"  {OUTPUT_FILE}"
)


# ============================================================
# 12. MOSTRAR TOP 20
# ============================================================

print()
print("=" * 70)
print("TOP 20 LEADS")
print("=" * 70)

for index, lead in enumerate(
    leads[:20],
    start=1
):

    print()

    print(
        f"{index}. "
        f"{lead['channel_name']}"
    )

    print(
        f"   Inscritos: "
        f"{lead['subscribers']:,}"
    )

    print(
        f"   Vídeos encontrados: "
        f"{lead['videos_found']}"
    )

    print(
        f"   Média de views: "
        f"{lead['average_views']:,}"
    )

    print(
        f"   Último vídeo: "
        f"{lead['last_video_date']}"
    )

    print(
        f"   Score: "
        f"{lead['score']}/10"
    )

    print(
        f"   {lead['channel_url']}"
    )


print()
print("=" * 70)
print("LEAD FINDER FINALIZADO")
print("=" * 70)