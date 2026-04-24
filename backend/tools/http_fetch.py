from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from backend.errors import DataTooLargeError, InputError, UnavailableError


async def fetch_to_disk(
    url: str,
    dest: Path,
    *,
    max_bytes: int,
    timeout: float = 60.0,
    allowed_content_types: Optional[tuple[str, ...]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Path:
    """Stream ``url`` to ``dest``, aborting if the body exceeds ``max_bytes``.

    Rejects non-http/https schemes at the boundary, enforces status and
    optional content-type, and maps httpx errors to RunItBack exception
    types. If the response exceeds ``max_bytes`` mid-stream, any
    partial file written to ``dest`` is removed before raising.
    """
    if not url.startswith(("http://", "https://")):
        raise InputError(f"only http/https URLs are allowed, got: {url!r}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    owned = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    try:
        try:
            async with client.stream("GET", url) as response:
                if response.status_code >= 500:
                    raise UnavailableError(
                        f"upstream {response.status_code} for {url!r}",
                        details={"status": response.status_code},
                    )
                if response.status_code >= 400:
                    raise InputError(
                        f"fetch failed: {response.status_code} for {url!r}",
                        details={"status": response.status_code},
                    )

                if allowed_content_types:
                    ct = response.headers.get("content-type", "")
                    if not any(a in ct for a in allowed_content_types):
                        raise InputError(
                            f"unexpected content-type {ct!r}",
                            details={
                                "content_type": ct,
                                "allowed": list(allowed_content_types),
                            },
                        )

                written = 0
                try:
                    with dest.open("wb") as f:
                        async for chunk in response.aiter_bytes():
                            written += len(chunk)
                            if written > max_bytes:
                                raise DataTooLargeError(
                                    f"response exceeded {max_bytes} bytes",
                                    details={
                                        "max_bytes": max_bytes,
                                        "url": url,
                                    },
                                )
                            f.write(chunk)
                except DataTooLargeError:
                    dest.unlink(missing_ok=True)
                    raise
                return dest
        except httpx.TimeoutException as e:
            raise UnavailableError(
                f"timeout fetching {url!r}", details={"timeout": timeout}
            ) from e
        except httpx.RequestError as e:
            raise UnavailableError(
                f"network error fetching {url!r}", details={"error": str(e)}
            ) from e
    finally:
        if owned:
            await client.aclose()
