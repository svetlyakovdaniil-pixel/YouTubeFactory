from app.core.factory import YouTubeFactory


def create_video(channel: str):

    factory = YouTubeFactory()

    return factory.run(channel)