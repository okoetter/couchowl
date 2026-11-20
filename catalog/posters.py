"""Poster proxy: images are downloaded from TMDB once and then served from disk.

TMDB image paths change whenever the image changes ("/gw8ZlIX….jpg"), so a cached
file never becomes outdated; a refreshed title simply points to a new file.
"""

import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from . import tmdb

# Sizes offered by TMDB that Couch Owl uses (width in pixels). Other sizes are refused,
# so the cache can't be filled with arbitrary variants. w780 is only loaded when someone
# enlarges a poster on a detail page.
POSTER_SIZES = ("w92", "w185", "w342", "w500", "w780")
# TMDB file names: letters, digits, and an image extension. Nothing else is accepted.
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}\.(jpg|jpeg|png|webp)$")
CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def is_valid(size: str, filename: str) -> bool:
    return size in POSTER_SIZES and FILENAME_PATTERN.fullmatch(filename) is not None


def content_type(filename: str) -> str:
    return CONTENT_TYPES[filename.rsplit(".", 1)[1]]


def poster_url(poster_path: str, size: str) -> str:
    """URL of our proxy for a TMDB poster path like '/abc.jpg' ('' if there is none)."""
    filename = poster_path.lstrip("/")
    if not poster_path or not is_valid(size, filename):
        return ""
    return reverse("catalog:poster", args=[size, filename])


def cached_poster(size: str, filename: str) -> Path:
    """Path of the poster on disk; downloads it from TMDB first if necessary.

    Raises tmdb.TMDBNotFound / tmdb.TMDBError if it can't be downloaded.
    """
    if not is_valid(size, filename):
        raise ValueError("Invalid poster size or file name")
    path = Path(settings.POSTER_CACHE_DIR) / size / filename
    if path.is_file():
        return path

    content, _content_type = tmdb.get_client().image(size, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file and rename it: other processes never see half a file
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(content)
    os.replace(temp.name, path)
    return path
