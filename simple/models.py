import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Literal, Optional


class DnsServerUpstreamProtocol(Enum):
    UDP = "udp"
    TCP = "tcp"
    HTTPS = "https"
    TLS = "tls"


@dataclass(kw_only=True, frozen=True)
class DnsServerUpstream:
    name: str
    ip: list[IPv4Address | IPv6Address]
    preferred_protocol: Optional[DnsServerUpstreamProtocol] = None
    ipv4: list[str] = field(init=False, compare=False)
    ipv6: list[str] = field(init=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "ipv4", [str(x) for x in self.ip if isinstance(x, IPv4Address)])
        object.__setattr__(self, "ipv6", [str(x) for x in self.ip if isinstance(x, IPv6Address)])


@dataclass(kw_only=True, frozen=True)
class DnsServerRulesConfig:
    allowed_ips: dict[str, list[str]] = field(default_factory=dict)
    allowed_names: dict[str, list[str]] = field(default_factory=dict)
    blocked_ips: dict[str, list[str]] = field(default_factory=dict)
    blocked_names: dict[str, list[str]] = field(default_factory=dict)
    cloaking_rules: dict[str, list[str]] = field(default_factory=dict)
    forwarding_rules: dict[str, list[str]] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True)
class DnsServerConfig:
    ipv6: Optional[bool]
    default: list[str]
    upstream: dict[str, DnsServerUpstream]
    rules: DnsServerRulesConfig = field(default_factory=DnsServerRulesConfig)


@dataclass(kw_only=True, frozen=True)
class RequestLog:
    request_id: str
    client_ip: str
    name: str
    cname: Optional[str]
    question_type: str
    response_status: Optional[str]
    server: Optional[str]
    ms: float
    error: Optional[str] = None
    created: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))


class CloakingItemRecordType(Enum):
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"

    def __conform__(self, protocol):
        if protocol is sqlite3.PrepareProtocol:
            return self.value

    def __str__(self):
        return self.value


@dataclass(kw_only=True, frozen=True)
class AllowedIpItem:
    group: str
    ip: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class AllowedNameItem:
    group: str
    name: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class BlockedIpItem:
    group: str
    ip: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class BlockedNameItem:
    group: str
    name: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class CloakingItem:
    group: str
    name: str
    record_type: CloakingItemRecordType
    mapped: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class ForwardingItem:
    group: str
    name: str
    use_glob: bool


@dataclass(kw_only=True, frozen=True)
class DnsServerRules:
    allowed_ips: list[AllowedIpItem] = field(default_factory=list)
    allowed_names: list[AllowedNameItem] = field(default_factory=list)
    blocked_ips: list[BlockedIpItem] = field(default_factory=list)
    blocked_names: list[BlockedNameItem] = field(default_factory=list)
    cloaking_rules: list[CloakingItem] = field(default_factory=list)
    forwarding_rules: list[ForwardingItem] = field(default_factory=list)


ServiceActionType = Literal["install", "start", "stop", "remove", "restart", "run"]


@dataclass(kw_only=True, frozen=True)
class AppArgs:
    data_dir: Path
    port: int = 53
    service: Optional[ServiceActionType] = None

    def __post_init__(self):
        object.__setattr__(self, "data_dir", self.data_dir.resolve())
