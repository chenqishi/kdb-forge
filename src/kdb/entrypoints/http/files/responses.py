from typing import Dict
from typing import Iterable
from typing import Optional
import kdb.shared.storage.runtime_state as runtime_state
import mimetypes

def _http_datetime_format(dt) -> Optional[str]:
    if not dt:
        return None
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _guess_media_type(object_path: str, fallback: str = "application/octet-stream") -> str:
    mime_type, _ = mimetypes.guess_type(object_path)
    return mime_type or fallback


def _format_last_modified(value) -> Optional[str]:
    try:
        return _http_datetime_format(value)
    except AttributeError:
        return None


def _extract_common_headers(metadata: Dict[str, object]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    cache_control = metadata.get("CacheControl") or runtime_state.DEFAULT_CACHE_CONTROL
    headers["Cache-Control"] = cache_control

    etag = metadata.get("ETag")
    if etag:
        headers["ETag"] = etag

    last_modified = _format_last_modified(metadata.get("LastModified"))
    if last_modified:
        headers["Last-Modified"] = last_modified

    content_length = metadata.get("ContentLength")
    if content_length is not None:
        headers["Content-Length"] = str(content_length)

    expires = metadata.get("Expires")
    if expires:
        expires_str = _format_last_modified(expires)
        if expires_str:
            headers["Expires"] = expires_str

    accept_ranges = metadata.get("AcceptRanges") or metadata.get("Accept-Ranges")
    if accept_ranges:
        headers["Accept-Ranges"] = accept_ranges
    else:
        headers["Accept-Ranges"] = "bytes"

    return headers


def _streaming_body_iter(body, chunk_size: int) -> Iterable[bytes]:
    try:
        for chunk in body.iter_chunks(chunk_size=chunk_size):
            if chunk:
                yield chunk
    finally:
        body.close()
