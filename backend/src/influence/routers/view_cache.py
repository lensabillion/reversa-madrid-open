"""HTTP caching for the read-only views: Cache-Control, validators and 304 Not Modified.

A view changes only when the pipeline rewrites its file, so a browser or a shared cache may
keep a copy for `INFLUENCE_VIEW_MAX_AGE` seconds and afterwards revalidate it with
`If-None-Match`; a matching validator answers 304 with no body instead of the whole view.
The validators come from file stats (`services/lineage_views.py`), never from the content,
so a revalidation costs one `stat` per view file and no read or parse.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from email.utils import formatdate
from importlib.metadata import version

from fastapi import Request

from influence.services.lineage_views import ViewStat

MAX_AGE_VARIABLE = "INFLUENCE_VIEW_MAX_AGE"
DEFAULT_MAX_AGE = 3600
# Error answers describe a moment (a missing or broken file), so no cache may keep them.
NO_STORE = {"Cache-Control": "no-store"}
# The response is the package's serialization of the files, so a deployment that changes
# that serialization must change the validator even when no file changed.
_VERSION = version("influence")
_WHOLE_SECONDS = re.compile(r"[0-9]+")


def max_age_from(environ: Mapping[str, str]) -> int:
    """The view max-age in seconds, from `INFLUENCE_VIEW_MAX_AGE` or the default.

    Read once at import, so a bad value stops the API at start with the variable's name
    rather than serving with a silently substituted default.
    """
    raw = environ.get(MAX_AGE_VARIABLE)
    if raw is None:
        return DEFAULT_MAX_AGE
    if _WHOLE_SECONDS.fullmatch(raw) is None:
        raise ValueError(
            f"{MAX_AGE_VARIABLE} must be a whole number of seconds, 0 or more; got {raw!r}"
        )
    return int(raw)


def etag(stats: Iterable[ViewStat]) -> str:
    """A strong entity tag for the response built from these view files.

    Hashing (slug, size, mtime_ns) of every file makes a listing's tag change when any
    view is added, rewritten or removed; for one view it is the same rule over one file.
    """
    digest = hashlib.sha256(_VERSION.encode())
    for stat in stats:
        digest.update(f"\n{stat.slug}\t{stat.size}\t{stat.mtime_ns}".encode())
    return f'"{digest.hexdigest()[:32]}"'


def validators(stats: tuple[ViewStat, ...], max_age: int) -> dict[str, str]:
    """Cache-Control, ETag and, when a file exists, Last-Modified from the newest one."""
    headers = {"Cache-Control": f"public, max-age={max_age}", "ETag": etag(stats)}
    if stats:
        newest = max(stat.mtime_ns for stat in stats)
        headers["Last-Modified"] = formatdate(newest / 1e9, usegmt=True)
    return headers


def not_modified(request: Request, current: str) -> bool:
    """Whether `If-None-Match` matches `current`, by RFC 9110 section 13.1.2.

    `*` matches any current representation; otherwise the field (possibly repeated) is a
    comma-separated list of entity tags compared weakly, ignoring a `W/` prefix, as the
    RFC requires for If-None-Match. Our tags hold no commas, so splitting on commas is safe.
    """
    tags = {
        tag.strip().removeprefix("W/")
        for field in request.headers.getlist("if-none-match")
        for tag in field.split(",")
    }
    return "*" in tags or current.removeprefix("W/") in tags
