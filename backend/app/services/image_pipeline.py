from __future__ import annotations

import hashlib
import mimetypes
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import imagehash
import requests
from PIL import Image, UnidentifiedImageError

from app.core.config import settings

warnings.simplefilter('ignore', Image.DecompressionBombWarning)


IMAGE_REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': f'{settings.legacy_mall_base_url.rstrip("/")}/',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
}

EXTENSION_BY_MIME = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
    'image/bmp': '.bmp',
    'image/tiff': '.tif',
}


@dataclass(slots=True)
class ArchivedImagePayload:
    resolved_url: str
    file_size: int
    mime_type: str | None
    width: int | None
    height: int | None
    file_ext: str
    sha256: str
    phash: str | None
    dhash: str | None
    storage_key: str


def get_archive_root() -> Path:
    root = Path(settings.image_archive_root)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    return root.resolve()


def normalize_remote_image_url(source_url: str) -> str:
    source_url = str(source_url or '').strip()
    if not source_url:
        return ''

    legacy_mall_base_url = settings.legacy_mall_base_url.rstrip('/')
    legacy_file_base_url = settings.legacy_file_base_url.rstrip('/')

    if source_url.startswith('http://') or source_url.startswith('https://'):
        if source_url.startswith(legacy_mall_base_url):
            return source_url.replace(legacy_mall_base_url, legacy_file_base_url, 1)
        return source_url

    if source_url.startswith('../'):
        source_url = source_url[3:]
    elif source_url.startswith('./'):
        source_url = source_url[2:]

    normalized = f'{legacy_mall_base_url}/{source_url.lstrip("/")}'
    return normalized.replace(legacy_mall_base_url, legacy_file_base_url, 1)


def detect_extension(resolved_url: str, mime_type: str | None, image_format: str | None) -> str:
    normalized_mime = (mime_type or '').split(';', 1)[0].strip().lower()
    if normalized_mime in EXTENSION_BY_MIME:
        return EXTENSION_BY_MIME[normalized_mime]

    suffix = Path(urlparse(resolved_url).path).suffix.lower()
    if suffix:
        return suffix

    if image_format:
        guessed = EXTENSION_BY_MIME.get(f'image/{image_format.lower()}')
        if guessed:
            return guessed

    return '.bin'


def build_storage_key(sha256: str, extension: str) -> str:
    extension = extension if extension.startswith('.') else f'.{extension}'
    extension = extension.lower()
    return f'product-images/{sha256[:2]}/{sha256}{extension}'


def archive_file_to_local_fs(file_bytes: bytes, storage_key: str) -> Path:
    archive_root = get_archive_root()
    target_path = archive_root / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        target_path.write_bytes(file_bytes)
    return target_path


def inspect_image(file_bytes: bytes) -> tuple[int | None, int | None, str | None, str | None, str | None]:
    try:
        with Image.open(BytesIO(file_bytes)) as image:
            width, height = image.size
            image_format = image.format
            phash = str(imagehash.phash(image))
            dhash = str(imagehash.dhash(image))
            return width, height, image_format, phash, dhash
    except (UnidentifiedImageError, OSError):
        return None, None, None, None, None


def download_and_archive_image(source_url: str, session: requests.Session | None = None) -> ArchivedImagePayload:
    resolved_url = normalize_remote_image_url(source_url)
    if not resolved_url:
        raise ValueError('empty resolved image url')

    client = session or requests.Session()
    response = client.get(
        resolved_url,
        headers=IMAGE_REQUEST_HEADERS,
        timeout=settings.image_request_timeout_seconds,
    )
    response.raise_for_status()

    mime_type = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower() or None
    if mime_type and not mime_type.startswith('image/'):
        raise ValueError(f'unexpected content-type: {mime_type}')

    file_bytes = response.content
    if not file_bytes:
        raise ValueError('empty image response body')

    sha256 = hashlib.sha256(file_bytes).hexdigest()
    width, height, image_format, phash, dhash = inspect_image(file_bytes)
    file_ext = detect_extension(resolved_url=resolved_url, mime_type=mime_type, image_format=image_format)
    storage_key = build_storage_key(sha256=sha256, extension=file_ext)
    archive_file_to_local_fs(file_bytes=file_bytes, storage_key=storage_key)

    normalized_mime = mime_type or mimetypes.guess_type(f'file{file_ext}')[0]
    return ArchivedImagePayload(
        resolved_url=resolved_url,
        file_size=len(file_bytes),
        mime_type=normalized_mime,
        width=width,
        height=height,
        file_ext=file_ext,
        sha256=sha256,
        phash=phash,
        dhash=dhash,
        storage_key=storage_key,
    )
