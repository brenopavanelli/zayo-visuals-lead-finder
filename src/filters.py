def filter_channels(
    channels,
    min_subscribers,
    max_subscribers,
    country=None,
    require_country=False
):
    """
    Filtra canais por quantidade de inscritos e país.
    """

    filtered = {}

    for channel_id, channel in channels.items():

        subscribers = channel.get("subscribers")

        # Sem número público de inscritos
        if subscribers is None:
            continue

        # Filtro de inscritos
        if subscribers < min_subscribers:
            continue

        if subscribers > max_subscribers:
            continue

        # Filtro de país
        if country:

            channel_country = channel.get(
                "country"
            )

            if require_country:

                if channel_country != country:
                    continue

            else:

                if (
                    channel_country is not None
                    and channel_country != country
                ):
                    continue

        filtered[channel_id] = channel

    return filtered