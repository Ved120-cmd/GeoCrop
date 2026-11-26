"""Outbound HTTP with SSRF protection. Every network fetch in GeoCrop goes through here.

Rules (all must hold, including for every redirect hop):
  * scheme is https;
  * the host is on the caller's allow-list (exact name, or a subdomain of an entry starting with ".");
  * every address the host resolves to is public (no loopback, private, link-local, CGNAT, multicast, reserved,
    or unspecified ranges; this also blocks cloud metadata endpoints such as 169.254.169.254);
  * redirects are followed manually (max 5) so each hop is re-checked.

DNS rebinding: the address is checked at resolution time; requests re-resolves on connect, so a hostile resolver
could still swap answers between the check and the connection. The host allow-list is the primary control; the IP
check is defence in depth.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests

# Hosts GeoCrop is allowed to contact (data providers named in docs/ and reports/). Keep this list explicit.
DATA_HOSTS = frozenset({
    "power.larc.nasa.gov",            # NASA POWER daily weather
    ".googleapis.com",                # Earth Engine downloads (earthengine.googleapis.com)
    "www.geoboundaries.org", "github.com", ".githubusercontent.com", "codeload.github.com", "api.github.com",
    "data.chc.ucsb.edu",              # CHIRPS
    "files.isric.org", "docs.isric.org",  # SoilGrids
    "imdpune.gov.in",                 # IMD gridded rain/temperature
    "niphm.gov.in", "ppqs.gov.in",    # official IPM packages, CIB&RC label claims
    "huggingface.co", ".hf.co",       # PlantVillage splits, timm weights
    "copernicus-dem-90m.s3.amazonaws.com",
    "data.ecmwf.int",                 # ECMWF open data
})


class BlockedRequest(ValueError):
    """Raised when a URL fails the SSRF checks."""


def _host_allowed(host: str, allowed) -> bool:
    host = host.lower().rstrip(".")
    for a in allowed:
        a = a.lower()
        if (a.startswith(".") and (host.endswith(a) or host == a[1:])) or host == a:
            return True
    return False


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified
                or (a.version == 4 and a in ipaddress.ip_network("100.64.0.0/10")))  # carrier-grade NAT


def check_url(url: str, allowed=DATA_HOSTS) -> str:
    """Return the URL if it passes every rule, else raise BlockedRequest."""
    p = urlsplit(url)
    if p.scheme != "https":
        raise BlockedRequest(f"only https is allowed: {url[:80]}")
    if not p.hostname or p.username or p.password:
        raise BlockedRequest("URL must have a host and no credentials")
    if not _host_allowed(p.hostname, allowed):
        raise BlockedRequest(f"host not on the allow-list: {p.hostname}")
    try:
        ip_literal = ipaddress.ip_address(p.hostname)
    except ValueError:
        ip_literal = None
    if ip_literal is not None:
        raise BlockedRequest("IP-address URLs are not allowed; use the provider's host name")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise BlockedRequest(f"cannot resolve {p.hostname}: {e}") from e
    bad = [i[4][0] for i in infos if not _public(i[4][0])]
    if bad:
        raise BlockedRequest(f"{p.hostname} resolves to a non-public address {bad[0]}")
    return url


def safe_request(method: str, url: str, *, allowed=DATA_HOSTS, session: requests.Session | None = None, max_redirects: int = 5,
                 timeout: float = 120, **kw) -> requests.Response:
    """requests.request with the SSRF rules applied to the URL and to every redirect target."""
    s = session or requests
    for _ in range(max_redirects + 1):
        check_url(url, allowed)
        r = s.request(method, url, allow_redirects=False, timeout=timeout, **kw)
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location")
            if not loc:
                return r
            r.close()
            url = urljoin(url, loc)
            if r.status_code == 303 or (r.status_code in (301, 302) and method.upper() == "POST"):
                method, kw = "GET", {k: v for k, v in kw.items() if k not in ("data", "json", "files")}
            continue
        return r
    raise BlockedRequest(f"too many redirects (>{max_redirects})")


def safe_get(url: str, **kw) -> requests.Response:
    return safe_request("GET", url, **kw)
