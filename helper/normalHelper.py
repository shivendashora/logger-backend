import re
import shutil
import uuid

from fastapi import UploadFile
import os

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# extension -> the only MIME type that extension may contain
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# the first bytes ("magic numbers") identify the real format, whatever the file name or browser claims
FILE_SIGNATURES = {
    "application/pdf": [b"%PDF-"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/gif": [b"GIF87a", b"GIF89a"],
}


def detect_file_type(header: bytes):
    for mime, signatures in FILE_SIGNATURES.items():
        if any(header.startswith(signature) for signature in signatures):
            return mime
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(file: UploadFile) -> str:
    # only PDFs and images are accepted; returns the verified MIME type or raises ValueError
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF or image files (png, jpg, gif, webp) are allowed")

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size == 0:
        raise ValueError("File is empty")
    if size > MAX_FILE_SIZE:
        raise ValueError("File must be 10 MB or smaller")

    header = file.file.read(12)
    file.file.seek(0)
    if detect_file_type(header) != ALLOWED_EXTENSIONS[extension]:
        raise ValueError("File content does not match its extension")

    return ALLOWED_EXTENSIONS[extension]


def original_file_name(file_path: str) -> str:
    # "<32 hex>_report.pdf" -> "report.pdf"
    return re.sub(r"^[0-9a-f]{32}_", "", os.path.basename(file_path))


def create_file_path(file : UploadFile , directory_path:str):
    # saves the upload inside directory_path and returns the saved file's path
    os.makedirs(directory_path, exist_ok = True)

    # basename strips any folders in the client's filename; the uuid prefix stops same-name uploads overwriting each other
    file_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename)}"
    filePath = os.path.join(directory_path, file_name)

    with open(filePath,"wb") as destination:
        shutil.copyfileobj(file.file,destination)

    return filePath

def clean_search_query(search_query: str) -> str:
    """
    Cleans the search query string:
    - Strips leading/trailing spaces
    - Collapses multiple spaces into one
    - Removes dangerous characters for SQL injection
    - Keeps only letters, numbers, spaces, and basic punctuation
    """
    if not search_query:
        return ""

    # Trim spaces
    cleaned = search_query.strip()

    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Remove unwanted characters (keep alphanumeric, space, ., -, _, @)
    cleaned = re.sub(r"[^a-zA-Z0-9\s\.\-\_@]", "", cleaned)

    return cleaned
