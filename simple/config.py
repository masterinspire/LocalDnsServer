import json
import logging
from ipaddress import ip_address
from typing import Optional, Callable

from simple.app_args import AppArgs
from simple.models import (
    AllowedIpItem,
    AllowedNameItem,
    BlockedIpItem,
    BlockedNameItem,
    CloakingItem,
    DnsServerConfig,
    DnsServerRules,
    DnsServerRulesConfig,
    DnsServerUpstream,
    DnsServerUpstreamProtocol,
    ForwardingItem,
)
from simple.parse_rules import (
    parse_allowed_ips,
    parse_allowed_names,
    parse_blocked_ips,
    parse_blocked_names,
    parse_cloaking_rules,
    parse_forwarding_rules,
)

logger = logging.getLogger(__name__)

__default_config_object__ = {
    "ipv6": False,
    "default": ["cloudflare", "google"],
    "upstream": {
        "cloudflare": ["1.0.0.1", "1.1.1.1", "2606:4700:4700::1001", "2606:4700:4700::1111"],
        "adguard": ["94.140.14.140", "94.140.14.141", "2a10:50c0::1:ff", "2a10:50c0::2:ff"],
        "opendns": ["208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53"],
        "quad9": ["9.9.9.10", "149.112.112.10", "2620:fe::10", "2620:fe::fe:10"],
        "google": {"ip": ["8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844"], "preferred_protocol": "udp"},
    },
    "rules": {
        "allowed_ips": "allowed-ips.txt",
        "allowed_names": "allowed-names.txt",
        "blocked_ips": "blocked-ips.txt",
        "blocked_names": {"default": "blocked-names.txt", "temp": "blocked-names-temp.txt"},
        "cloaking_rules": "cloaking-rules.txt",
        "forwarding_rules": {"google": "forwarding-rules.txt"},
    },
}


def parse_config_from_object(o: dict) -> DnsServerConfig:
    for key in ["upstream", "rules"]:
        o[key] = {} if o.get(key) is None else o[key]
        if not isinstance(o[key], dict):
            raise ValueError(key)

    o["default"] = [] if o.get("default") is None else o["default"]

    upstream_server: dict[str, DnsServerUpstream] = dict()

    ipv6 = o.get("ipv6")

    # ///////////////////////////////////
    for key, value in o["upstream"].items():
        preferred_protocol = None
        ip = []
        if isinstance(value, list):
            ip = [ip_address(x) for x in value]
        elif isinstance(value, dict):
            if isinstance(value["ip"], list):
                ip = [ip_address(x) for x in value["ip"]]

            preferred_protocol_str = value.get("preferred_protocol")
            preferred_protocol_str = None if preferred_protocol_str is None else str(preferred_protocol_str)
            if preferred_protocol_str is not None:
                try:
                    preferred_protocol = DnsServerUpstreamProtocol(preferred_protocol_str)
                except ValueError:
                    message = f"upstream -> {key}: preferred_protocol {preferred_protocol_str} should be one of (udp, tcp, https, tls)"
                    raise ValueError(message) from None
        else:
            raise ValueError("upstream -> {}: wrong value".format(key))

        if len(ip) == 0:
            raise ValueError("upstream -> {}: no ip set".format(key))

        upstream_server[key] = DnsServerUpstream(name=key, ip=ip, preferred_protocol=preferred_protocol)

    if len(upstream_server) == 0:
        raise ValueError("no upstream server set")

    # ///////////////////////////////////
    default_server_list = list()
    for w2 in o["default"]:
        if (item2 := upstream_server.get(w2)) is None:
            raise ValueError("default: upstream {} not found".format(w2))

        default_server_list.append(item2.name)

    if len(default_server_list) == 0:
        raise ValueError("no default upstream set")

    # ///////////////////////////////////
    dns_server_rules: dict = o["rules"]
    dns_server_rules2: list[dict[str, list[str]]] = []
    for w3 in ["allowed_ips", "allowed_names", "blocked_ips", "blocked_names", "cloaking_rules", "forwarding_rules"]:
        value3 = dict()
        item3: Optional[str | list[str] | dict[str, str | list[str]]] = dns_server_rules.get(w3)
        if item3 is not None:
            if isinstance(item3, str):
                value3["default"] = [item3]
            elif isinstance(item3, list):
                value3["default"] = [x for x in item3]
            elif isinstance(item3, dict):
                for key4, value4 in item3.items():
                    if isinstance(value4, str):
                        value3[str(key4)] = [value4]
                    elif isinstance(value4, list):
                        value3[str(key4)] = [x for x in value4]
                    else:
                        raise ValueError("rules -> {} -> {}: wrong value".format(w3, key4))
            else:
                raise ValueError("rules -> {}: wrong value".format(w3))

        for key5, value5 in value3.items():
            if not key5 or not value5 or not all(str(x).endswith(".txt") for x in value5):
                raise ValueError("rules -> {} -> {}: {}".format(w3, key5, value5))

        dns_server_rules2.append(value3)

    allowed_ips, allowed_names, blocked_ips, blocked_names, cloaking_rules, forwarding_rules = dns_server_rules2

    for key5, _ in forwarding_rules.items():
        if upstream_server.get(key5) is None:
            raise ValueError("rules -> forwarding_rules: upstream server {} not found".format(key5))

    rules = DnsServerRulesConfig(
        allowed_ips=allowed_ips,
        allowed_names=allowed_names,
        blocked_ips=blocked_ips,
        blocked_names=blocked_names,
        cloaking_rules=cloaking_rules,
        forwarding_rules=forwarding_rules,
    )

    dns_server_config = DnsServerConfig(ipv6=ipv6, default=default_server_list, upstream=upstream_server, rules=rules)

    return dns_server_config


class ConfigFile:
    def __init__(self, app_args: AppArgs):
        self.app_args = app_args

    def read_config_from_config_file(self) -> DnsServerConfig:
        logger.info(f"data dir: {self.app_args.data_dir}")
        custom_config_file = self.app_args.data_dir.joinpath("config.json")
        if custom_config_file.is_file():
            logger.info(f"using config file: {custom_config_file}")
            config_file = custom_config_file
            with open(config_file, "rb") as f:
                o: dict = json.load(f)
        else:
            o = __default_config_object__

        return parse_config_from_object(o)

    def init_db_from_config(self, config: DnsServerConfig):
        rules = self.read_dns_server_rules(config)

        from simple.db import TheDbJob

        db_job = TheDbJob()
        db_job.init_db(rules)
        db_job.db.close()

    def read_dns_server_rules(self, config: DnsServerConfig) -> DnsServerRules:
        for key, _ in config.rules.forwarding_rules.items():
            if config.upstream.get(key) is None:
                raise ValueError("rules -> forwarding_rules: upstream server {} not found".format(key))

        def read_file1(file1: dict[str, list[str]], parse_func: Callable[[str, str], list]) -> list:
            result = []
            for key1, value1 in file1.items():
                for value11 in value1:
                    p = self.app_args.data_dir.joinpath(value11).resolve()
                    if p.is_file():
                        text = p.read_text()
                        result.extend(parse_func(key1, text))
                    else:
                        logger.warning(f"missing {key1} -> {value11}")

            return result

        allowed_ips: list[AllowedIpItem] = read_file1(config.rules.allowed_ips, parse_allowed_ips)
        allowed_names: list[AllowedNameItem] = read_file1(config.rules.allowed_names, parse_allowed_names)
        blocked_ips: list[BlockedIpItem] = read_file1(config.rules.blocked_ips, parse_blocked_ips)
        blocked_names: list[BlockedNameItem] = read_file1(config.rules.blocked_names, parse_blocked_names)
        cloaking_rules: list[CloakingItem] = read_file1(config.rules.cloaking_rules, parse_cloaking_rules)
        forwarding_rules: list[ForwardingItem] = read_file1(config.rules.forwarding_rules, parse_forwarding_rules)

        return DnsServerRules(
            allowed_ips=allowed_ips,
            allowed_names=allowed_names,
            blocked_ips=blocked_ips,
            blocked_names=blocked_names,
            cloaking_rules=cloaking_rules,
            forwarding_rules=forwarding_rules,
        )
