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