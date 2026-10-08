# urlbert/urlbert2/core/net_safety.py
# 사용자가 보낸 URL로 서버가 직접 접속할 때 SSRF를 막기 위한 공통 검사 함수

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443, 8080, 8443}
MAX_REDIRECTS = 5


def is_public_hostname(hostname: str) -> bool:
    """호스트가 가리키는 모든 IP가 공인 IP일 때만 True (사설·루프백·링크로컬·메타데이터 주소 차단)."""
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return True


def is_safe_public_url(url: str) -> bool:
    """http/https 이고, 허용된 포트이며, 공인 IP로만 해석되는 URL인지 확인."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in ALLOWED_SCHEMES or port not in ALLOWED_PORTS:
        return False
    return is_public_hostname(parsed.hostname)


def safe_get(url: str, max_redirects: int = MAX_REDIRECTS, **kwargs) -> requests.Response:
    """리다이렉트를 직접 따라가며 매 단계마다 목적지를 검사하는 requests.get 대체 함수."""
    kwargs["allow_redirects"] = False
    current = url
    for _ in range(max_redirects + 1):
        if not is_safe_public_url(current):
            raise requests.exceptions.InvalidURL(f"blocked non-public URL: {current}")
        response = requests.get(current, **kwargs)
        location = response.headers.get("Location")
        if not (response.is_redirect and location):
            return response
        current = urljoin(current, location)
    raise requests.exceptions.TooManyRedirects(f"too many redirects: {url}")
