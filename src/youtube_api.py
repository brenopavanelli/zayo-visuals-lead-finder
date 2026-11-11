import os

from dotenv import load_dotenv
from googleapiclient.discovery import build


load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")


def create_youtube_client():
    """
    Cria e retorna o cliente da YouTube Data API.
    """

    if not API_KEY:
        raise ValueError(
            "YOUTUBE_API_KEY não encontrada no arquivo .env"
        )

    return build(
        "youtube",
        "v3",
        developerKey=API_KEY
    )


def search_videos(
    query,
    published_after,
    max_pages=2,
    max_results=50
):
    """
    Pesquisa vídeos recentes no YouTube.

    Retorna uma lista de resultados da busca.
    """

    youtube = create_youtube_client()

    videos = []
    page_token = None

    for page in range(max_pages):

        request = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            publishedAfter=published_after,
            order="date",
            maxResults=max_results,
            pageToken=page_token
        )

        response = request.execute()

        items = response.get("items", [])

        videos.extend(items)

        print(
            f"    Página {page + 1}: "
            f"{len(items)} vídeos"
        )

        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return videos


def get_channel_details(channel_ids):
    """
    Busca informações de vários canais.

    A API aceita até 50 IDs por chamada.
    """

    youtube = create_youtube_client()

    channels = {}

    # Divide os IDs em grupos de 50
    for i in range(0, len(channel_ids), 50):

        batch = channel_ids[i:i + 50]

        request = youtube.channels().list(
            part="snippet,statistics",
            id=",".join(batch)
        )

        response = request.execute()

        for channel in response.get("items", []):

            channel_id = channel["id"]

            snippet = channel.get("snippet", {})
            statistics = channel.get("statistics", {})

            subscriber_count = statistics.get(
                "subscriberCount"
            )

            # subscriberCount pode não estar disponível
            if subscriber_count is not None:
                subscriber_count = int(subscriber_count)

            channels[channel_id] = {
                "channel_id": channel_id,
                "channel_name": snippet.get(
                    "title",
                    "Desconhecido"
                ),
                "country": snippet.get(
                    "country"
                ),
                "subscribers": subscriber_count,
                "video_count": int(
                    statistics.get("videoCount", 0)
                ),
            }

    return channels


def get_video_statistics(video_ids):
    """
    Busca estatísticas dos vídeos.

    Retorna:
        {
            video_id: {
                "channel_id": ...,
                "title": ...,
                "published_at": ...,
                "views": ...
            }
        }
    """

    youtube = create_youtube_client()

    videos = {}

    # A API aceita até 50 IDs por chamada
    for i in range(0, len(video_ids), 50):

        batch = video_ids[i:i + 50]

        request = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch)
        )

        response = request.execute()

        for video in response.get("items", []):

            video_id = video["id"]

            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})

            views = statistics.get(
                "viewCount",
                0
            )

            videos[video_id] = {
                "video_id": video_id,
                "channel_id": snippet.get(
                    "channelId"
                ),
                "title": snippet.get(
                    "title",
                    ""
                ),
                "published_at": snippet.get(
                    "publishedAt"
                ),
                "views": int(views)
            }

    return videos


# ============================================================
# DETECÇÃO DE CANAIS "SHORTS ONLY"
# ============================================================

import re


def parse_iso_duration(iso_duration):
    """
    Converte duração ISO 8601 (ex.: PT1M5S, PT45S) para segundos.
    """
    if not iso_duration:
        return 0

    match = re.match(
        r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",
        iso_duration
    )

    if not match:
        return 0

    days, hours, minutes, seconds = (
        int(g) if g else 0
        for g in match.groups()
    )

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def get_channel_recent_videos(channel_id, max_results=20):
    """
    Busca os vídeos mais recentes do canal (via playlist de uploads).

    Retorna lista de dicts: {video_id, duration_sec, title}.
    """

    youtube = create_youtube_client()

    # 1. Descobrir a playlist de uploads do canal
    channels_resp = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()

    items = channels_resp.get("items", [])

    if not items:
        return []

    uploads_playlist = items[0]["contentDetails"][
        "relatedPlaylists"
    ].get("uploads")

    if not uploads_playlist:
        return []

    # 2. Buscar os últimos vídeos enviados
    playlist_resp = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist,
        maxResults=min(max_results, 50)
    ).execute()

    video_ids = [
        item["contentDetails"]["videoId"]
        for item in playlist_resp.get("items", [])
    ]

    if not video_ids:
        return []

    # 3. Buscar duração/título desses vídeos
    videos_resp = youtube.videos().list(
        part="contentDetails,snippet",
        id=",".join(video_ids)
    ).execute()

    recent = []

    for video in videos_resp.get("items", []):

        duration_sec = parse_iso_duration(
            video.get("contentDetails", {}).get("duration", "")
        )

        recent.append({
            "video_id": video["id"],
            "duration_sec": duration_sec,
            "title": video.get("snippet", {}).get("title", "")
        })

    return recent


def classify_channel_format(channel_id, shorts_threshold_sec=60):
    """
    Classifica o formato do canal analysando os vídeos recentes.

    Um vídeo é considerado Short se tiver duração <= shorts_threshold_sec
    (60s) — padrão do YouTube Shorts.

    Retorna:
        {
            "tipo": "shorts_only" | "long" | "misto" | "desconhecido",
            "shorts_ratio": float (0..1) ou None,
            "shorts_count": int,
            "total_recent": int
        }
    """

    recent = get_channel_recent_videos(channel_id, max_results=20)

    if not recent:
        return {
            "tipo": "desconhecido",
            "shorts_ratio": None,
            "shorts_count": 0,
            "total_recent": 0
        }

    shorts_count = sum(
        1
        for video in recent
        if video["duration_sec"] <= shorts_threshold_sec
    )

    ratio = shorts_count / len(recent)

    if ratio >= 0.8:
        tipo = "shorts_only"
    elif ratio == 0:
        tipo = "long"
    else:
        tipo = "misto"

    return {
        "tipo": tipo,
        "shorts_ratio": round(ratio, 2),
        "shorts_count": shorts_count,
        "total_recent": len(recent)
    }