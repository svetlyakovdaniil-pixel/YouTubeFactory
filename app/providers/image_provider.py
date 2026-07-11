from pathlib import Path
import random

from app.utils.image_cache import prepare_image


class ImageProvider:

    def __init__(self, config):

        self.config = config

        self.images_path = Path(
            "/opt/youtubefactory/library"
        ) / config["name"] / "images"

    def get_images(self, count=None):

        images = []

        for extension in (
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.webp",
        ):

            images.extend(self.images_path.glob(extension))
            images.extend(self.images_path.glob(extension.upper()))

        random.shuffle(images)

        images = [
            prepare_image(image)
            for image in images
        ]

        if count:

            images = images[:count]

        return images