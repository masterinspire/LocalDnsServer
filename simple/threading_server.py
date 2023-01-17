import errno
import logging
import random
import socket
import socketserver
import struct
import uuid
from ipaddress import ip_address, IPv4Address
from typing import Any, cast, Optional

import dns.exception
import dns.message
import dns.query
import dns.rdata
import dns.rdtypes
import dns.rdtypes.IN
import dns.rdtypes.IN.A
import dns.rdtypes.IN.AAAA
import dns.resolver
import httpx

from simple.db import TheDbJob
from simple.models import (
    AllowedIpItem,
    BlockedIpItem,
    BlockedNameItem,
    CloakingItemRecordType,
    DnsServerConfig,
    DnsServerUpstreamProtocol,
    RequestLog,
)
from simple.stopwatch import Stopwatch

logger = logging.getLogger(__name__)


class DnsRequestHandler(socketserver.BaseRequestHandler):
    def __init__(self, request: Any, client_address: Any, server: socketserver.BaseServer):
        self.config = cast(DnsServerConfig, None)
        self.doh_client = cast(httpx.Client, None)
        self.db = TheDbJob(readonly=True)
        self.request_id: str = str(uuid.uuid4())
        self._request_domain: Optional[str] = None
        self.request_domain_cname: Optional[str] = None
        super().__init__(request, client_address, server)
        self.upstream_server_used: Optional[str] = None

    @property
    def client_ip(self):
        return self.client_address[0]

    @property
    def request_domain(self) -> str:
        if self._request_domain is None:
            raise ValueError("request_domain?!")

        return self._request_domain

    @request_domain.setter
    def request_domain(self, value: str):
        if value is None:
            raise ValueError("request_domain?!")

        self._request_domain = value

    def setup(self) -> None:
        server = cast(ThreadingDnsUDPServer | ThreadingDnsTCPServer, self.server)
        self.config = server.config
        self.doh_client = server.doh_client
        self.upstream_server_used = None

    def _get_request(self) -> Optional[bytes]:
        if self.server.socket_type == socket.SOCK_STREAM:
            connection = cast(socket.socket, self.request)
            if len((data := connection.recv(8192))) < 2:
                # print("Request Truncated")
                return None

            length = struct.unpack("!H", data[:2])[0]
            while len(data) - 2 < length:
                if not (new_data := connection.recv(8192)):
                    break
                data += new_data
            data = data[2:]
            return data
        elif self.server.socket_type == socket.SOCK_DGRAM:
            data, _ = cast(tuple[bytes, socket.socket], self.request)
            return data

        return None

    def _send_response(self, response_message: dns.message.Message):
        response_data = response_message.to_wire()
        if self.server.socket_type == socket.SOCK_STREAM:
            connection = cast(socket.socket, self.request)
            response_data = struct.pack("!H", len(response_data)) + response_data
            connection.sendall(response_data)
        elif self.server.socket_type == socket.SOCK_DGRAM:
            _, connection = cast(tuple[bytes, socket.socket], self.request)
            connection.sendto(response_data, self.client_address)

    def _make_response(self, request_message: dns.message.Message, rcode: Optional[dns.rcode.Rcode]) -> dns.message.Message:
        response_message = dns.message.make_response(request_message)
        if rcode is not None:
            response_message.set_rcode(rcode)

        return response_message

    def _blocked_names(self, domain: str, request_message: dns.message.Message) -> Optional[dns.message.Message]:
        question: dns.rrset.RRset = request_message.question[0]
        response_message: Optional[dns.message.Message] = None
        if question.rdtype == dns.rdatatype.ANY:
            response_message = self._make_response(request_message, dns.rcode.REFUSED)
        else:
            if (item := self.db.block_names_ex(client_ip=self.client_ip, name=domain)) is not None:
                if isinstance(item, BlockedNameItem):
                    response_message = self._make_response(request_message, dns.rcode.REFUSED)

        return response_message

    def _cloaking(self, domain: str, request_message: dns.message.Message) -> dns.message.Message:
        question: dns.rrset.RRset = request_message.question[0]
        cloaking_items = self.db.cloaking_rules_ex(domain)
        record_type = CloakingItemRecordType.A if question.rdtype == dns.rdatatype.A else CloakingItemRecordType.AAAA
        records = [
            dns.rdata.from_text(dns.rdataclass.IN, question.rdtype, x.mapped) for x in cloaking_items if x.record_type == record_type
        ]
        if len(records) == 0:
            if (cname := next((x for x in cloaking_items if x.record_type == CloakingItemRecordType.CNAME), None)) is None:
                response_message = self._proxy_request(name=domain, request_message=request_message)
            else:
                self.request_domain_cname = cname.mapped
                request_message2: Optional[dns.message.Message] = dns.message.from_text(request_message.to_text())
                question2: dns.rrset.RRset = request_message2.question[0]
                question2.name = dns.name.from_text(self.request_domain_cname)
                if (response_message := self._blocked_names(self.request_domain_cname, request_message2)) is None:
                    response_message = self._proxy_request(self.request_domain_cname, request_message2)
                    response_message.question[0].name = question.name
                    response_message.additional.clear()
                    response_message.authority.clear()
                    if response_message.rcode() == dns.rcode.NOERROR:
                        response_message.answer = [
                            x for x in response_message.answer if cast(dns.rrset.RRset, x).rdtype != dns.rdatatype.CNAME
                        ]
                        for w in response_message.answer:
                            w = cast(dns.rrset.RRset, w)
                            if w.rdtype == dns.rdatatype.A or w.rdtype == dns.rdatatype.AAAA:
                                w.name = question.name

                        if len(response_message.answer) == 0:
                            response_message.set_rcode(dns.rcode.NXDOMAIN)
        else:
            if len(records) > 2:
                random.shuffle(records)

            response_message = self._make_response(request_message, dns.rcode.NOERROR)
            response_message.answer.append(dns.rrset.from_rdata_list(question.name, 900, records))

        return response_message

    def _insert_request_log(self, question_type: str, response_status: Optional[str], ms: float, error: Optional[str] = None):
        self.db.insert_request_log_into_queue(
            RequestLog(
                request_id=self.request_id,
                client_ip=self.client_ip,
                name=self.request_domain,
                cname=self.request_domain_cname,
                question_type=question_type,
                response_status=response_status,
                server=self.upstream_server_used,
                ms=ms,
                error=error,
            )
        )

    def _blocked_ips(self, response_message: dns.message.Message) -> None:
        has_removed_any_items = False
        for item in response_message.answer:
            item = cast(dns.rrset.RRset, item)
            if item.rdtype != dns.rdatatype.A and item.rdtype != dns.rdatatype.AAAA:
                continue

            items_to_remove = []
            for x in item:
                if not isinstance(x, dns.rdtypes.IN.A.A | dns.rdtypes.IN.AAAA.AAAA):
                    continue

                if (item2 := self.db.block_ips_ex(client_ip=self.client_ip, ip=str(x.address))) is not None:
                    if isinstance(item2, AllowedIpItem):
                        pass
                    elif isinstance(item2, BlockedIpItem):
                        items_to_remove.append(x)

            for w in items_to_remove:
                has_removed_any_items = True
                item.remove(w)

        if has_removed_any_items:
            response_message.answer = [x for x in response_message.answer if len(cast(dns.rrset.RRset, x)) != 0]
            if len(response_message.answer) == 0 or (
                all(cast(dns.rrset.RRset, x).rdtype == dns.rdatatype.CNAME for x in response_message.answer)
            ):
                response_message.answer.clear()
                response_message.authority.clear()
                response_message.additional.clear()
                response_message.set_rcode(dns.rcode.REFUSED)

    def handle(self):
        if (data := self._get_request()) is None:
            return

        try:
            request_message = dns.message.from_wire(data, question_only=True, one_rr_per_rrset=False)
        except Exception:
            return

        if self.config.ipv6 is False and self.server.address_family == socket.AF_INET6:
            response_message = self._make_response(request_message, dns.rcode.NOTIMP)
            self._send_response(response_message)
            return

        # ///////////////////////////////////
        # https://www.iana.org/assignments/dns-parameters/dns-parameters.xhtml

        try:
            if isinstance(request_message, dns.message.QueryMessage) and request_message.opcode() == dns.opcode.QUERY:
                with Stopwatch() as stopwatch:
                    question: dns.rrset.RRset = request_message.question[0]
                    self.request_domain = str(question.name).rstrip(".")
                    is_a_aaaa_question = question.rdtype == dns.rdatatype.A or question.rdtype == dns.rdatatype.AAAA
                    if (response_message := self._blocked_names(domain=self.request_domain, request_message=request_message)) is None:
                        response_message = (
                            self._cloaking(domain=self.request_domain, request_message=request_message)
                            if is_a_aaaa_question
                            else self._proxy_request(name=self.request_domain, request_message=request_message)
                        )

                    if response_message is not None and is_a_aaaa_question and response_message.rcode() == dns.rcode.NOERROR:
                        self._blocked_ips(response_message)

                if self.upstream_server_used is None and response_message is not None:
                    self._insert_request_log(
                        question_type=dns.rdatatype.RdataType(question.rdtype).name,
                        response_status=dns.rcode.Rcode(response_message.rcode()).name,
                        ms=stopwatch.elapsed_milliseconds,
                    )
            else:
                response_message = self._make_response(request_message, dns.rcode.NOTIMP)
        except Exception as e:
            response_message = self._make_response(request_message, dns.rcode.SERVFAIL)
            logger.error(msg="??", exc_info=e)

        if response_message is None:
            response_message = self._make_response(request_message, dns.rcode.SERVFAIL)

        # ///////////////////////////////////
        self._send_response(response_message)

    def _dns_query(self, request_message: dns.message.Message, server_ip: str,
                   preferred_protocol: DnsServerUpstreamProtocol) -> dns.message.Message:
        if preferred_protocol == DnsServerUpstreamProtocol.UDP:
            response_message = dns.query.udp_with_fallback(request_message, where=server_ip, timeout=2, one_rr_per_rrset=False)
            if isinstance(response_message, tuple):
                response_message = response_message[0]

            return response_message
        elif preferred_protocol == DnsServerUpstreamProtocol.TCP:
            return dns.query.tcp(request_message, where=server_ip, timeout=2, one_rr_per_rrset=False)
        elif preferred_protocol == DnsServerUpstreamProtocol.HTTPS:
            return dns.query.https(request_message, where=server_ip, timeout=2, one_rr_per_rrset=False, session=self.doh_client)
        elif preferred_protocol == DnsServerUpstreamProtocol.TLS:
            return dns.query.tls(request_message, where=server_ip, timeout=2, one_rr_per_rrset=False)

        raise ValueError("!!!!!!!!!!")

    def _dns_query_with_upstream(self, request_message: dns.message.Message, upstream_name: str) -> Optional[dns.message.Message]:
        upstream = self.config.upstream[upstream_name]
        preferred_protocol = DnsServerUpstreamProtocol.HTTPS if upstream.preferred_protocol is None else upstream.preferred_protocol
        if self.server.address_family == socket.AF_INET:
            where = upstream.ipv4
        elif self.server.address_family == socket.AF_INET6:
            where = upstream.ipv6
        else:
            return None

        for ip in where:
            self.upstream_server_used = f"{preferred_protocol.value}://{ip}"
            upstream_server_error: Optional[str] = None
            response_message: Optional[dns.message.Message] = None

            try:
                with Stopwatch() as stopwatch:
                    response_message = self._dns_query(request_message, ip, preferred_protocol)

                return response_message
            except Exception as e:
                e = e.__context__ if isinstance(e, KeyError) and isinstance(e.__context__, httpx.RemoteProtocolError) else e
                s = str(e)
                type_name = type(e).__name__
                upstream_server_error = f"{type_name}: {s}"
                domain = "{}{}".format(self.request_domain, "" if self.request_domain_cname is None else f" -> {self.request_domain_cname}")
                # ConnectionAbortedError        [Errno 10053] Unknown error
                # ConnectionResetError          [WinError 10054] An existing connection was forcibly closed by the remote host
                # EOFError
                # KeyError: 1                   RemoteProtocolError
                # OSError                       [Errno 10051] Unknown error
                # OSError                       [Errno 10065] Unknown error
                # TimeoutError                  timed out
                # dns.exception.Timeout         The DNS operation timed out.
                # httpx.ConnectError            [WinError 10051] A socket operation was attempted to an unreachable network
                # httpx.ConnectError            [WinError 10053] An established connection was aborted by the software in your host machine
                # httpx.ConnectError            [WinError 10054] An existing connection was forcibly closed by the remote host
                # httpx.ConnectError            [WinError 10065] A socket operation was attempted to an unreachable host
                # httpx.ConnectTimeout          _ssl.c:980: The handshake operation timed out
                # httpx.ConnectTimeout          timed out
                # httpx.LocalProtocolError      Invalid input StreamInputs.SEND_END_STREAM in state StreamState.HALF_CLOSED_LOCAL
                # httpx.ReadTimeout             The read operation timed out
                # httpx.RemoteProtocolError     <ConnectionTerminated error_code:ErrorCodes.PROTOCOL_ERROR
                # httpx.RemoteProtocolError     Server disconnected
                # httpx.RemoteProtocolError     Server disconnected without sending a response.

                # httpx.LocalProtocolError      Received pseudo-header in trailer {b':scheme', b':path', b':method', b':authority'}
                # httpx.ReadError               [SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac (_ssl.c:2548)

                match e:
                    case TimeoutError() | dns.exception.Timeout() | httpx.ConnectTimeout() | httpx.ReadTimeout():
                        pass
                    case httpx.ConnectError() if (
                        s.find("A socket operation was attempted to an unreachable network") != -1
                        or s.find("A socket operation was attempted to an unreachable host") != -1
                        or s.find("An existing connection was forcibly closed by the remote host") != -1
                        or s.find("An established connection was aborted by the software in your host machine") != -1
                    ):
                        pass
                    case httpx.LocalProtocolError() if s.find("StreamState.HALF_CLOSED_LOCAL") != -1:
                        pass
                    case httpx.RemoteProtocolError() if s.startswith("Server disconnected") or s.startswith("<ConnectionTerminated"):
                        # TCP RESET
                        pass
                    case OSError() as ee if ee.errno in [errno.ENETUNREACH, errno.EHOSTUNREACH]:
                        pass
                    case ConnectionResetError() | EOFError() | ConnectionAbortedError():
                        pass
                    case _:
                        logger.error(f"{domain} -> {preferred_protocol.value}://{ip} {type_name}", exc_info=e)
            finally:
                question: dns.rrset.RRset = request_message.question[0]
                self._insert_request_log(
                    question_type=dns.rdatatype.RdataType(question.rdtype).name,
                    response_status=None if response_message is None else dns.rcode.Rcode(response_message.rcode()).name,
                    ms=stopwatch.elapsed_milliseconds,
                    error=upstream_server_error,
                )

        return None

    def _proxy_request(self, name: str, request_message: dns.message.Message) -> dns.message.Message:
        response_message: Optional[dns.message.Message] = None
        if (forwarding_item := self.db.forwarding_rules(name)) is None:
            for w in self.config.default:
                if (response_message := self._dns_query_with_upstream(request_message, w)) is not None:
                    break
        else:
            response_message = self._dns_query_with_upstream(request_message, forwarding_item.group)

        if response_message is None:
            response_message = self._make_response(request_message, dns.rcode.SERVFAIL)

        return response_message


def _get_address_family_from_host(host: str) -> Optional[socket.AddressFamily]:
    try:
        a = ip_address(host)
    except ValueError:
        return None
    else:
        return socket.AF_INET if isinstance(a, IPv4Address) else socket.AF_INET6


class ThreadingDnsTCPServer(socketserver.ThreadingTCPServer):
    def __init__(self, server_address: tuple[str, int], config: DnsServerConfig, doh_client: httpx.Client):
        self.daemon_threads = True
        self.config = config
        self.doh_client = doh_client
        if address_family := _get_address_family_from_host(server_address[0]):
            self.address_family = address_family

        super().__init__(server_address, DnsRequestHandler)


class ThreadingDnsUDPServer(socketserver.ThreadingUDPServer):
    def __init__(self, server_address: tuple[str, int], config: DnsServerConfig, doh_client: httpx.Client):
        self.daemon_threads = True
        self.config = config
        self.doh_client = doh_client
        if address_family := _get_address_family_from_host(server_address[0]):
            self.address_family = address_family

        super().__init__(server_address, DnsRequestHandler)