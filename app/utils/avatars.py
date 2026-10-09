"""Private, bounded profile pictures; always store a newly encoded image."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from app.utils.cloud_storage import cloud_storage_enabled, upload_cloud_file, cloud_file_path, remove_cloud_file

MAX_BYTES = 2 * 1024 * 1024


def avatar_path(filename):
    if not filename or Path(filename).name != filename or not filename.endswith('.png'):
        raise ValueError('Invalid picture filename.')
    if cloud_storage_enabled():
        path = cloud_file_path('avatar', filename, MAX_BYTES)
        if path:
            return path
        return Path(current_app.instance_path) / 'storage-cache' / 'missing' / filename
    folder = Path(current_app.instance_path) / 'uploads' / 'avatars'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / filename


def save_avatar(upload):
    content = upload.stream.read(MAX_BYTES + 1)
    if not content or len(content) > MAX_BYTES:
        raise ValueError('Choose a picture no larger than 2 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Use a still JPEG, PNG, or WebP picture.')
                if max(source.size) > 4096:
                    raise ValueError('Picture dimensions must not exceed 4096 × 4096 pixels.')
                source.load()
                picture = ImageOps.exif_transpose(source).convert('RGB')
                picture = ImageOps.fit(picture, (256, 256))
                clean = Image.new('RGB', picture.size)
                clean.paste(picture)
                filename = uuid4().hex + '.png'
                if cloud_storage_enabled():
                    output = BytesIO()
                    clean.save(output, format='PNG')
                    upload_cloud_file('avatar', filename, output.getvalue(), 'image/png', MAX_BYTES)
                else:
                    clean.save(avatar_path(filename), format='PNG')
                return filename
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('That file is not a supported, valid picture.') from exc


def remove_avatar(filename):
    if filename:
        if cloud_storage_enabled():
            remove_cloud_file('avatar', filename)
            return
        avatar_path(filename).unlink(missing_ok=True)
