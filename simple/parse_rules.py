import logging
from ipaddress import ip_address, IPv4Address
from typing import Optional

from simple.models import (
    AllowedIpItem,
    AllowedNameItem,
    BlockedIpItem,
    BlockedNameItem,
    CloakingItem,
    CloakingItemRecordType,
    ForwardingItem,
)

logger = logging.getLogger(__name__)


def parse_line(text: Optional[str]) -> list[str]:
    if not text:
        return list()

    result = set()
    comment = "#"
    lines = text.strip().splitlines()
    for line in lines:
        if not line or (i := line.find(comment)) == 0:
            continue

        if line := (line if i == -1 else line[0:i]).strip():
            result.add(line)

    return list(sorted(result))


def _parse_line_2(text: str) -> list[str]:
    lines = parse_line(text)
    return [x.lower() for x in lines if x.find(" ") == -1]


def parse_allowed_ips(group: str, text: str) -> list[AllowedIpItem]:
    return [AllowedIpItem(group=group, ip=x, use_glob=_should_use_glob(x)) for x in _parse_line_2(text)]


def parse_allowed_names(group: str, text: str) -> list[AllowedNameItem]:
    return [AllowedNameItem(group=group, name=x, use_glob=_should_use_glob(x)) for x in _parse_line_2(text)]


def parse_blocked_ips(group: str, text: str) -> list[BlockedIpItem]:
    return [BlockedIpItem(group=group, ip=x, use_glob=_should_use_glob(x)) for x in _parse_line_2(text)]


def parse_blocked_names(group: str, text: str) -> list[BlockedNameItem]:
    return [BlockedNameItem(group=group, name=x, use_glob=_should_use_glob(x)) for x in _parse_line_2(text)]


def parse_forwarding_rules(group: str, text: str) -> list[ForwardingItem]:
    return [ForwardingItem(group=group, name=x, use_glob=_should_use_glob(x)) for x in _parse_line_2(text)]


def parse_cloaking_rules(group: str, text: str) -> list[CloakingItem]:
    lines = parse_line(text)
    result: list[CloakingItem] = list()
    for line in lines:
        split = line.lower().split(" ")
        split = [x.strip() for x in split if x]
        split = [x for x in split if x]
        if len(split) != 2:
            logger.warning(f"parse_cloaking_rules {group}, line ignored: {line}")
            continue

        name, mapped = split
        if name == mapped:
            logger.warning(f"parse_cloaking_rules {group}, line ignored: {line}")
            continue

        try:
            ip = ip_address(mapped)
        except ValueError:
            if _should_use_glob(mapped):
                logger.warning(f"parse_cloaking_rules {group}, line ignored: {line}")
                continue

            record_type = CloakingItemRecordType.CNAME
        else:
            record_type = CloakingItemRecordType.A if isinstance(ip, IPv4Address) else CloakingItemRecordType.AAAA

        result.append(CloakingItem(group=group, name=name, record_type=record_type, mapped=mapped, use_glob=_should_use_glob(name)))

    result = list(set(result))

    def key(x: CloakingItem) -> tuple[str, str, str]:
        return x.group, x.name, x.mapped

    result.sort(key=key)
    return result


def _should_use_glob(s: str):
    for c in "*?[]":
        if s.find(c) != -1:
            return True

    return False
