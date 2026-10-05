"""The address of the party that actually connected (EMAIL-2).

Production topology: client -> nginx (same host) -> uvicorn on 127.0.0.1.
nginx sends `X-Forwarded-For: $proxy_add_x_forwarded_for`, i.e. whatever the
client put in that header FOLLOWED BY the address nginx saw. Only the entries
appended by our own proxies are facts; everything to their left is text typed
by the client.

So the header is read from the RIGHT: trusted proxy addresses are skipped and
the first address that is not one of ours is the client. A forged left-most
value is never used. The header is consulted only when the TCP peer itself is a
trusted proxy; a direct connection is identified by its socket address alone.

`X-Real-IP` and `Forwarded` are not read: nothing is gained from them and each
additional header is one more thing a deployment has to remember to overwrite.

TRUSTED_PROXY_IPS: comma separated addresses or CIDR ranges (default: loopback).
"""
from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Optional, Tuple

from starlette.requests import HTTPConnection

UNKNOWN = "unknown"
_DEFAULT_TRUSTED = "127.0.0.1,::1"


@lru_cache(maxsize=8)
def _networks(raw: str) -> Tuple[ipaddress._BaseNetwork, ...]:
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue        # a malformed entry trusts nothing
    return tuple(networks)


def _parse(value: Optional[str]) -> Optional[ipaddress._BaseAddress]:
    text = (value or "").strip()
    if text.startswith("[") and "]" in text:            # [v6]:port
        text = text[1:text.index("]")]
    elif text.count(":") == 1:                          # v4:port
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped or address


def is_trusted_proxy(value: Optional[str]) -> bool:
    address = _parse(value)
    if address is None:
        return False
    return any(address in network for network in _networks(os.getenv("TRUSTED_PROXY_IPS", _DEFAULT_TRUSTED)))


def client_ip(request: HTTPConnection) -> str:
    """Client address for rate limiting and audit. Never raises."""
    peer = request.client.host if request.client else None
    if not peer:
        return UNKNOWN
    if not is_trusted_proxy(peer):
        return str(_parse(peer) or peer)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        for candidate in reversed(forwarded.split(",")):
            address = _parse(candidate)
            if address is None:
                break                                   # garbage next to our proxy: stop, trust nothing further left
            if not is_trusted_proxy(str(address)):
                return str(address)
    return str(_parse(peer) or peer)
