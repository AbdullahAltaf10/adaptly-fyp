"""
URL safety for website ingestion (SSRF protection).

The prototype fetched any URL the user pasted. That is a Server-Side Request
Forgery hole: the request comes from the *server*, so it reaches anything the
server can reach, including things the user cannot.

Concretely, a user could paste:

    http://localhost:8000/users/directory    -> our own internal API
    http://169.254.169.254/latest/meta-data/ -> cloud instance credentials
    http://192.168.1.1/                      -> devices on the host's network
    file:///etc/passwd                       -> local files

and the extracted "article text" would be handed straight back to them.

Two rules close it:
  1. Only http and https. No file://, ftp://, gopher:// and so on.
  2. Resolve the hostname and refuse if it points anywhere private.

Resolving DNS *before* fetching also blocks the rebinding trick, where a
public-looking hostname resolves to a private address.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

ALLOWED_SCHEMES = {"http", "https"}

# The cloud metadata endpoints. These are the highest-value SSRF targets
# because they can hand out credentials.
BLOCKED_HOSTS = {
    "169.254.169.254",   # AWS / Azure / GCP instance metadata
    "metadata.google.internal",
    "metadata",
}

MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024   # 5 MB of HTML is already excessive
REQUEST_TIMEOUT_SECONDS = 10


def _is_private(ip_text: str) -> bool:
    """True for anything not routable on the public internet."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True   # unparseable: refuse rather than guess
    return (
        ip.is_private          # 10.x, 172.16-31.x, 192.168.x
        or ip.is_loopback      # 127.x, ::1
        or ip.is_link_local    # 169.254.x — includes cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    """
    Check a user-supplied URL before the server fetches it.

    Returns the URL if safe; raises HTTPException with a message that does not
    leak internal network detail.
    """
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="No URL was provided.")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail="Only http and https links are supported.",
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="That does not look like a valid URL.")

    if hostname in BLOCKED_HOSTS or hostname.endswith(".internal") or hostname == "localhost":
        raise HTTPException(status_code=400, detail="That address cannot be fetched.")

    # Resolve the name and check EVERY address it maps to. Checking only the
    # first would let a host with one public and one private record through.
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="That website could not be found.")

    for entry in resolved:
        ip_text = entry[4][0]
        if _is_private(ip_text):
            # Deliberately vague: confirming "this resolved to 192.168.1.1"
            # would turn the endpoint into a network scanner.
            raise HTTPException(status_code=400, detail="That address cannot be fetched.")

    return url
