from datetime import datetime, timezone


def calculate_score(
    average_views,
    subscribers,
    videos_found,
    last_video_date
):
    """
    Calcula um score de 0 a 10 para priorizar leads.

    Quanto maior:
        maior potencial de prospecção.
    """

    score = 0

    # ========================================================
    # 1. RECÊNCIA
    # ========================================================

    if last_video_date:

        last_date = datetime.fromisoformat(
            last_video_date.replace(
                "Z",
                "+00:00"
            )
        )

        now = datetime.now(timezone.utc)

        days_since_upload = (
            now - last_date
        ).days

        if days_since_upload <= 3:
            score += 3

        elif days_since_upload <= 7:
            score += 2

        elif days_since_upload <= 30:
            score += 1

    # ========================================================
    # 2. VIEWS / INSCRITOS
    # ========================================================

    if subscribers and subscribers > 0:

        views_ratio = (
            average_views / subscribers
        )

        if views_ratio >= 1:
            score += 3

        elif views_ratio >= 0.5:
            score += 2

        elif views_ratio >= 0.2:
            score += 1

    # ========================================================
    # 3. FREQUÊNCIA
    # ========================================================

    if videos_found >= 10:
        score += 2

    elif videos_found >= 5:
        score += 1

    # ========================================================
    # RESULTADO
    # ========================================================

    return min(score, 10)