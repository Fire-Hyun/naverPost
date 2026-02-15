"""
Minimal DNS fallback resolver for unstable WSL/local DNS environments.

This module patches socket.getaddrinfo for selected hosts and performs
direct UDP DNS A-record queries to public resolvers when system DNS fails.
"""

from __future__ import annotations

import os
import random
import socket
import struct
import threading
import time
import logging
from typing import Dict, List, Optional, Sequence, Tuple


_PATCH_LOCK = threading.Lock()
_PATCHED = False
_ORIGINAL_GETADDRINFO = socket.getaddrinfo


class _CacheEntry:
    def __init__(self, ips: List[str], expire_at: float):
        self.ips = ips
        self.expire_at = expire_at


_DNS_CACHE: Dict[str, _CacheEntry] = {}
_LOG = logging.getLogger(__name__)
_DEFAULT_TELEGRAM_API_IPS = [
    "149.154.167.220",
    "149.154.167.51",
    "149.154.167.50",
    "149.154.167.91",
    "149.154.167.92",
]


def _encode_qname(host: str) -> bytes:
    labels = host.strip(".").split(".")
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in labels) + b"\x00"


def _skip_name(packet: bytes, offset: int) -> int:
    while True:
        if offset >= len(packet):
            return offset
        length = packet[offset]
        if length == 0:
            return offset + 1
        # DNS compression pointer
        if (length & 0xC0) == 0xC0:
            return offset + 2
        offset += 1 + length


def _query_dns_a(host: str, server: str, timeout_s: float = 1.5) -> List[str]:
    txid = random.getrandbits(16)
    flags = 0x0100  # standard query, recursion desired
    qdcount = 1
    header = struct.pack("!HHHHHH", txid, flags, qdcount, 0, 0, 0)
    question = _encode_qname(host) + struct.pack("!HH", 1, 1)  # A / IN
    packet = header + question

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_s)
    try:
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(2048)
    finally:
        sock.close()

    if len(data) < 12:
        return []

    resp_txid, resp_flags, qd, an, _, _ = struct.unpack("!HHHHHH", data[:12])
    if resp_txid != txid:
        return []
    rcode = resp_flags & 0x000F
    if rcode != 0 or an == 0:
        return []

    offset = 12
    for _ in range(qd):
        offset = _skip_name(data, offset)
        offset += 4  # qtype + qclass
        if offset > len(data):
            return []

    ips: List[str] = []
    for _ in range(an):
        offset = _skip_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, rclass, ttl, rdlength = struct.unpack("!HHIH", data[offset:offset + 10])
        offset += 10
        if offset + rdlength > len(data):
            break
        rdata = data[offset:offset + rdlength]
        offset += rdlength

        if rtype == 1 and rclass == 1 and rdlength == 4:
            ips.append(socket.inet_ntoa(rdata))

    return ips


def _resolve_with_public_dns(host: str, dns_servers: Sequence[str]) -> List[str]:
    now = time.time()
    cached = _DNS_CACHE.get(host)
    if cached and cached.expire_at > now:
        return list(cached.ips)

    all_ips: List[str] = []
    for server in dns_servers:
        try:
            ips = _query_dns_a(host, server)
            for ip in ips:
                if ip not in all_ips:
                    all_ips.append(ip)
            if all_ips:
                break
        except Exception:
            continue

    if all_ips:
        _DNS_CACHE[host] = _CacheEntry(all_ips, now + 300)  # 5 min cache
    return all_ips


def install_dns_fallback(
    target_hosts: Optional[Sequence[str]] = None,
    dns_servers: Optional[Sequence[str]] = None,
) -> None:
    """
    Patch socket.getaddrinfo with fallback DNS resolution for target hosts.

    Environment override:
      TELEGRAM_DNS_SERVERS="1.1.1.1,8.8.8.8"
      TELEGRAM_API_IPS="149.154.167.220,149.154.167.50"
    """
    global _PATCHED
    with _PATCH_LOCK:
        if _PATCHED:
            return

        targets = {h.lower() for h in (target_hosts or ["api.telegram.org"])}
        env_dns = os.getenv("TELEGRAM_DNS_SERVERS", "").strip()
        if env_dns:
            servers = [s.strip() for s in env_dns.split(",") if s.strip()]
        else:
            servers = list(dns_servers or ["1.1.1.1", "8.8.8.8", "9.9.9.9"])
        static_ips = [
            ip.strip()
            for ip in os.getenv("TELEGRAM_API_IPS", "").split(",")
            if ip.strip()
        ]

        original = _ORIGINAL_GETADDRINFO

        def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            try:
                return original(host, port, family, type, proto, flags)
            except socket.gaierror:
                host_str = (host.decode() if isinstance(host, bytes) else str(host)).lower()
                if host_str not in targets:
                    raise

                # Only fallback for IPv4-capable requests.
                if family not in (0, socket.AF_UNSPEC, socket.AF_INET):
                    raise

                ips = _resolve_with_public_dns(host_str, servers)
                if not ips and static_ips:
                    ips = list(static_ips)
                    _LOG.warning(
                        "DNS fallback using TELEGRAM_API_IPS for %s (system resolver failed)",
                        host_str,
                    )
                if not ips and host_str == "api.telegram.org":
                    ips = list(_DEFAULT_TELEGRAM_API_IPS)
                    _LOG.warning(
                        "DNS fallback using built-in Telegram API IP pool for %s",
                        host_str,
                    )
                if not ips:
                    raise

                results = []
                for ip in ips:
                    try:
                        resolved = original(ip, port, socket.AF_INET, type, proto, flags)
                        results.extend(resolved)
                    except socket.gaierror:
                        continue
                if results:
                    _LOG.warning(
                        "DNS fallback resolved %s via public DNS: %s",
                        host_str,
                        ", ".join(ips),
                    )
                    return results
                raise

        socket.getaddrinfo = _patched_getaddrinfo
        _PATCHED = True
