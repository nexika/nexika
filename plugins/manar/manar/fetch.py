"""Safe HTTP fetching for untrusted sites.

- http/https only; redirects recorded (max 5).
- Every connection goes to the IP address that was checked (no DNS-rebinding window), and
  private, loopback, link-local, shared (100.64/10), multicast and reserved addresses are refused
  unless allow_local=True (needed to audit a dev server such as http://localhost:3000).
- Bounded: 3 MB per response (also after gzip/deflate decompression) and a total deadline, so a
  slow-drip server or a compression bomb can't hang or exhaust memory.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field

from . import USER_AGENT

MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = 15
CHUNK = 64 * 1024


class FetchError(Exception):
    pass


@dataclass
class Response:
    url: str                 # final URL after redirects
    status: int
    headers: dict[str, str]
    body: str
    redirects: list[str] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


def _blocked(ip: ipaddress._BaseAddress) -> bool:
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
            or ip.is_unspecified or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network(
                "100.64.0.0/10")))


def resolve_checked(host: str, port: int, allow_local: bool) -> list[tuple]:
    """Addresses to try, in order. A host with any blocked address is refused entirely."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {host}: {exc}") from None
    addresses = []
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0].split("%")[0])
        if not allow_local and _blocked(ip):
            raise FetchError(f"{host} resolves to a private address ({ip}); "
                             "use --allow-local to audit a local server")
        addresses.append((family, sockaddr))
    if not addresses:
        raise FetchError(f"cannot resolve {host}")
    return addresses


def _check_scheme(url: str) -> None:
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise FetchError(f"only http/https URLs are fetched: {url}")


def _opener(allow_local: bool, chain: list[str]) -> urllib.request.OpenerDirector:
    def pinned_socket(conn) -> socket.socket:
        error: OSError | None = None
        for family, sockaddr in resolve_checked(conn.host, conn.port, allow_local):
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(conn.timeout if conn.timeout is not None else TIMEOUT)
            try:
                sock.connect(sockaddr)   # the checked address itself: no second DNS lookup
                return sock
            except OSError as exc:       # e.g. IPv6 first but the server only listens on IPv4
                sock.close()
                error = exc
        raise error or OSError(f"cannot connect to {conn.host}")

    class PinnedHTTP(http.client.HTTPConnection):
        def connect(self):
            self.sock = pinned_socket(self)

    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            self.sock = self._context.wrap_socket(pinned_socket(self), server_hostname=self.host)

    class HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(PinnedHTTP, req)

    class HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(PinnedHTTPS, req, context=self._context)

    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _check_scheme(newurl)
            chain.append(newurl)
            if len(chain) > 5:
                raise FetchError(f"too many redirects from {req.full_url}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(HTTPHandler, HTTPSHandler, Redirects)


def _decompress(raw: bytes, encoding: str) -> bytes:
    """Undo gzip/deflate with the output capped at MAX_BYTES. Some servers compress unasked."""
    encoding = encoding.lower()
    if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
        attempts = (31,)
    elif "deflate" in encoding:
        attempts = (15, -15)  # zlib-wrapped, or raw deflate
    else:
        return raw
    for wbits in attempts:
        try:
            return zlib.decompressobj(wbits).decompress(raw, MAX_BYTES)
        except zlib.error:
            continue
    return raw


def _read(resp, deadline: float) -> bytes:
    data = bytearray()
    while len(data) <= MAX_BYTES:
        chunk = resp.read(CHUNK)
        if not chunk:
            break
        data += chunk
        if time.monotonic() > deadline:
            raise FetchError("response too slow (total time limit exceeded)")
    return bytes(data[: MAX_BYTES + 1])


def _text(raw: bytes, charset: str | None) -> str:
    try:
        return raw.decode(charset or "utf-8", "replace")
    except LookupError:  # unknown charset name sent by the server
        return raw.decode("utf-8", "replace")


def get(url: str, allow_local: bool = False, accept: str = "text/html,*/*;q=0.8",
        timeout: int = TIMEOUT) -> Response:
    _check_scheme(url)
    chain: list[str] = []
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept,
                                                   "Accept-Encoding": "gzip, deflate"})
    deadline = time.monotonic() + timeout * 2
    try:
        with _opener(allow_local, chain).open(request, timeout=timeout) as resp:
            raw = _read(resp, deadline)
            status, final, headers = resp.status, resp.geturl(), resp.headers
    except urllib.error.HTTPError as exc:
        raw = _read(exc, deadline) if exc.fp else b""
        status, final, headers = exc.code, exc.geturl() or url, exc.headers
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, FetchError):
            raise exc.reason from None
        raise FetchError(f"{url}: {exc.reason}") from None
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        raise FetchError(f"{url}: {exc}") from None
    body = _decompress(raw[:MAX_BYTES], headers.get("Content-Encoding", "") if headers else "")
    return Response(
        url=final, status=status,
        headers={k.lower(): v for k, v in (headers.items() if headers else [])},
        body=_text(body[:MAX_BYTES], headers.get_content_charset() if headers else None),
        redirects=chain,
    )


def origin(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
