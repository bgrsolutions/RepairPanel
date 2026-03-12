import os
import uuid
from pathlib import Path

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def save_intake_file(upload_root: str, intake_reference: str, file_obj: FileStorage) -> tuple[str, int | None]:
    original_name = secure_filename(file_obj.filename or "upload.bin")
    extension = Path(original_name).suffix.lower()
    if extension and extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported file type")

    folder = Path(upload_root) / "intake" / intake_reference
    folder.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    destination = folder / unique_name
    file_obj.save(destination)

    size = os.path.getsize(destination) if destination.exists() else None
    return str(destination), size
