import queue
import sqlite3
from dataclasses import asdict, fields
from typing import Optional

from simple.app_args import app_args
from simple.models import (
    AllowedIpItem,
    AllowedNameItem,
    BlockedIpItem,
    BlockedNameItem,
    CloakingItem,
    CloakingItemRecordType,
    DnsServerRules,
    ForwardingItem,
    RequestLog,
)

__pragma_user_version__ = 1


# noinspection DuplicatedCode
class TheDbJob:
    request_log_queue = queue.Queue()

    def __init__(self, in_memory: bool = False, readonly: bool = False):
        if in_memory:
            connection_str = "file:db?mode=memory"
        else:
            current_dir_data_db_file = app_args.data_dir.joinpath("data.sqlite3")
            connection_str = "file:{}?mode={}".format(current_dir_data_db_file, "ro" if readonly else "rwc")

        self.db = sqlite3.connect(connection_str, uri=True, timeout=1)
        self.db.row_factory = sqlite3.Row

    def pragma_user_version(self, user_version: Optional[int] = None):
        if user_version is None:
            sql = """ pragma user_version """
            row = self.db.execute(sql).fetchone()
            return row["user_version"]

        sql = """ pragma user_version = {} """.format(user_version)
        self.db.execute(sql)
        self.db.commit()
        return user_version

    def __init_db_pragma(self):
        sql = """ pragma journal_mode=wal """
        self.db.execute(sql)
        self.db.commit()

    def __init_db_schema_1(self):
        sql = """
            drop table if exists allowed_ips;
            drop table if exists allowed_names;
            drop table if exists blocked_ips;
            drop table if exists blocked_names;
            drop table if exists cloaking_rules;
            drop table if exists forwarding_rules;
        """
        self.db.executescript(sql)
        self.db.commit()

    def __init_db_schema_2(self):
        sql = """

        create table if not exists request_logs
        (
            "id"              integer primary key autoincrement,
            "request_id"      text not null,
            "client_ip"       text not null,
            "name"            text not null,
            "cname"           text null,
            "question_type"   text not null,
            "response_status" text null,
            "server"          text null,
            "ms"              real not null,
            "error"           text null,
            "created"         text not null default current_timestamp
        );

        create table allowed_ips
        (
            "id"       integer primary key autoincrement,
            "group"    text not null,
            "use_glob" bool not null,
            "ip"       text not null,
            constraint "group_ip" unique ("group", "ip") on conflict ignore
        );

        create table allowed_names
        (
            "id"       integer primary key autoincrement,
            "group"    text not null,
            "use_glob" bool not null,
            "name"     text not null,
            constraint "group_name" unique ("group", "name") on conflict ignore
        );

        create table blocked_ips
        (
            "id"       integer primary key autoincrement,
            "group"    text not null,
            "use_glob" bool not null,
            "ip"       text not null,
            constraint "group_ip" unique ("group", "ip") on conflict ignore
        );

        create table blocked_names
        (
            "id"       integer primary key autoincrement,
            "group"    text not null,
            "use_glob" bool not null,
            "name"     text not null,
            constraint "group_name" unique ("group", "name") on conflict ignore
        );

        create table cloaking_rules
        (
            "id"          integer primary key autoincrement,
            "group"       text not null,
            "name"        text not null,
            "use_glob"    bool not null,
            "record_type" text not null,
            "mapped"      text not null,
            constraint "group_name" unique ("group", "name", "record_type", "mapped") on conflict ignore
        );

        create table forwarding_rules
        (
            "id"       integer primary key autoincrement,
            "group"    text not null,
            "use_glob" bool not null,
            "name"     text not null,
            constraint "group_name" unique ("group", "name") on conflict ignore
        );

        """

        self.db.executescript(sql)
        self.db.commit()

    def __init_db_dns_server_rules(self, rules: DnsServerRules):
        sql = """ insert into allowed_ips("group", "use_glob", "ip") values (:group, :use_glob, :ip) """
        self.db.executemany(sql, [asdict(item) for item in rules.allowed_ips])
        self.db.commit()

        sql = """ insert into allowed_names ("group", "use_glob", "name") values (:group, :use_glob, :name) """
        self.db.executemany(sql, [asdict(item) for item in rules.allowed_names])
        self.db.commit()

        sql = """ insert into blocked_ips ("group", "use_glob", "ip") values (:group, :use_glob, :ip) """
        self.db.executemany(sql, [asdict(item) for item in rules.blocked_ips])
        self.db.commit()

        sql = """ insert into blocked_names ("group", "use_glob", "name") values (:group, :use_glob, :name) """
        self.db.executemany(sql, [asdict(item) for item in rules.blocked_names])
        self.db.commit()

        sql = """ insert into cloaking_rules ("group", "name", "use_glob", "record_type", "mapped")
                                                       values (:group, :name, :use_glob, :record_type, :mapped) """
        self.db.executemany(sql, [asdict(item) for item in rules.cloaking_rules])
        self.db.commit()

        sql = """ insert into forwarding_rules ("group", "use_glob", "name") values (:group, :use_glob, :name) """
        self.db.executemany(sql, [asdict(item) for item in rules.forwarding_rules])
        self.db.commit()

    def __init_db_upgrade(self):
        user_version = self.pragma_user_version()
        if user_version == __pragma_user_version__:
            return

        for w in range(user_version, __pragma_user_version__):
            if w == 0:
                self.__init_db_upgrade_db_0_1()

        self.pragma_user_version(__pragma_user_version__)

    def __init_db_upgrade_db_0_1(self):
        pass

    def init_db(self, rules: DnsServerRules):
        self.__init_db_pragma()
        self.__init_db_schema_1()
        self.__init_db_schema_2()
        self.__init_db_dns_server_rules(rules)
        self.__init_db_upgrade()

    def allowed_ips(self, client_ip: str, ip: str) -> Optional[AllowedIpItem]:
        parameters = {"client_ip": client_ip, "ip": ip}
        sql = """
            select * from allowed_ips where (
                        "group" in ('default', 'temp') or
                        ("group" not in ('default', 'temp') and :client_ip glob "group")
                    ) and (
                        ("use_glob" = true and :ip glob "ip") or
                        ("use_glob" = false and "ip" = :ip)
                    )
                order by id
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [AllowedIpItem(**{field.name: field.type(row[field.name]) for field in fields(AllowedIpItem)}) for row in rows]
        item = next((row for row in result if row.ip == ip), None)
        item = item if item is not None else next((x for x in result if x.group not in ["default", "temp"]), None)
        item = item if item is not None else next((x for x in result), None)
        return item

    def allowed_names(self, client_ip: str, name: str) -> Optional[AllowedNameItem]:
        if not name:
            return None

        parameters = {"client_ip": client_ip, "name": name.lower()}
        sql = """
            select * from allowed_names where (
                        "group" in ('default', 'temp') or
                        ("group" not in ('default', 'temp') and :client_ip glob "group")
                    ) and (
                        ("use_glob" = true and (:name glob "name" or :name glob '*.' || "name")) or
                        ("use_glob" = false and (:name like '%.' || "name" or "name" = '=' || :name or "name" = :name))
                    )
                order by id
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [AllowedNameItem(**{field.name: field.type(row[field.name]) for field in fields(AllowedNameItem)}) for row in rows]
        item = next((row for row in result if row.name.startswith("=")), None)
        item = item if item is not None else next((row for row in result if row.name == name), None)
        item = item if item is not None else next((x for x in result if x.group not in ["default", "temp"]), None)
        item = item if item is not None else next((x for x in result), None)
        return item

    def blocked_ips(self, client_ip: str, ip: str) -> Optional[BlockedIpItem]:
        parameters = {"client_ip": client_ip, "ip": ip}
        sql = """
            select * from blocked_ips where (
                        "group" in ('default', 'temp') or
                        ("group" not in ('default', 'temp') and :client_ip glob "group")
                    ) and (
                        ("use_glob" = true and :ip glob "ip") or
                        ("use_glob" = false and "ip" = :ip)
                    )
                order by id
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [BlockedIpItem(**{field.name: field.type(row[field.name]) for field in fields(BlockedIpItem)}) for row in rows]
        item = next((row for row in result if row.ip == ip), None)
        item = item if item is not None else next((x for x in result if x.group not in ["default", "temp"]), None)
        item = item if item is not None else next((x for x in result), None)
        return item

    def blocked_names(self, client_ip: str, name: str) -> Optional[BlockedNameItem]:
        if not name:
            return None

        parameters = {"client_ip": client_ip, "name": name.lower()}
        sql = """
            select * from blocked_names where (
                        "group" in ('default', 'temp') or
                        ("group" not in ('default', 'temp') and :client_ip glob "group")
                    ) and (
                        ("use_glob" = true and (:name glob "name" or :name glob '*.' || "name")) or
                        ("use_glob" = false and (:name like '%.' || "name" or "name" = '=' || :name or "name" = :name))
                    )
                order by id
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [BlockedNameItem(**{field.name: field.type(row[field.name]) for field in fields(BlockedNameItem)}) for row in rows]
        item = next((row for row in result if row.name.startswith("=")), None)
        item = item if item is not None else next((row for row in result if row.name == name), None)
        item = item if item is not None else next((x for x in result if x.group not in ["default", "temp"]), None)
        item = item if item is not None else next((x for x in result), None)
        return item

    def block_ips_ex(self, client_ip: str, ip: str) -> AllowedIpItem | BlockedIpItem | None:
        result1 = self.allowed_ips(client_ip, ip)
        return result1 if result1 is not None else self.blocked_ips(client_ip, ip)

    def block_names_ex(self, client_ip: str, name: str) -> AllowedNameItem | BlockedNameItem | None:
        result1 = self.allowed_names(client_ip, name)
        return result1 if result1 is not None else self.blocked_names(client_ip, name)

    def cloaking_rules(self, name: str) -> list[CloakingItem]:
        if not name:
            return []

        parameters = {"name": name.lower()}
        sql = """
            select * from cloaking_rules where
                    ("use_glob" = true and (:name glob "name" or :name glob '*.' || "name")) or
                    ("use_glob" = false and (:name like '%.' || "name" or "name" = '=' || :name or "name" = :name))
                order by random()
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [CloakingItem(**{field.name: field.type(row[field.name]) for field in fields(CloakingItem)}) for row in rows]
        item = next((row for row in result if row.name.startswith("=")), None)
        item = item if item is not None else next((row for row in result if row.name == name), None)
        item = item if item is not None else (None if len(result) <= 1 else max(result, key=self._max_len_by_name))
        item = item if item is not None else next((x for x in result), None)
        return [] if item is None else [x for x in result if x.name == item.name]

    def cloaking_rules_ex(self, name: str) -> list[CloakingItem]:
        result = self.cloaking_rules(name=name)
        for w in range(5):
            if (cname := next((x for x in result if x.record_type == CloakingItemRecordType.CNAME), None)) is None:
                break

            if len((result2 := self.cloaking_rules(name=cname.mapped))) == 0:
                break

            result = result2

        return result[:5]

    def forwarding_rules(self, name: str) -> Optional[ForwardingItem]:
        if not name:
            return None

        parameters = {"name": name.lower()}
        sql = """
            select * from forwarding_rules where
                    ("use_glob" = true and (:name glob "name" or :name glob '*.' || "name")) or
                    ("use_glob" = false and (:name like '%.' || "name" or "name" = '=' || :name or "name" = :name))
                order by id
        """
        rows = self.db.execute(sql, parameters).fetchall()
        result = [ForwardingItem(**{field.name: field.type(row[field.name]) for field in fields(ForwardingItem)}) for row in rows]
        item = next((row for row in result if row.name.startswith("=")), None)
        item = item if item is not None else next((row for row in result if row.name == name), None)
        item = item if item is not None else (None if len(result) <= 1 else max(result, key=self._max_len_by_name))
        item = item if item is not None else next((x for x in result), None)
        return item

    def insert_request_log_into_queue(self, request_log: RequestLog):
        TheDbJob.request_log_queue.put_nowait(request_log)

    def insert_request_log(self, *request_logs: RequestLog):
        # sqlite3.OperationalError: database is locked
        sql = """
            insert into request_logs
                        ("request_id", "client_ip", "name", "cname", "response_status", "question_type", "server", "ms", "error", "created")
                 values (:request_id, :client_ip, :name, :cname, :response_status, :question_type, :server, :ms, :error, :created)
        """
        self.db.executemany(sql, [asdict(x) for x in request_logs])
        self.db.commit()

    @staticmethod
    def _max_len_by_name(x: ForwardingItem | AllowedNameItem | BlockedNameItem | CloakingItem) -> int:
        return len(x.name)
