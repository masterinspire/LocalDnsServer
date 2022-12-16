import unittest
from typing import final

from simple.db import TheDbJob, __pragma_user_version__
from simple.models import (
    AllowedIpItem,
    AllowedNameItem,
    BlockedIpItem,
    CloakingItem,
    CloakingItemRecordType,
    DnsServerRules,
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


@final
class DnsServerDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        group_default = "default"
        group_ip_1 = "192.168.1.100"
        allowed_ips_group_default_text = """
            10.10.10.1[1-2]
        """
        allowed_ips_group_ip_1_text = """
            10.10.10.10
        """
        allowed_ips = parse_allowed_ips(group_default, allowed_ips_group_default_text)
        allowed_ips.extend(parse_allowed_ips(group_ip_1, allowed_ips_group_ip_1_text))
        # ///////////////////////////////////
        blocked_ips = parse_blocked_ips(group_default, allowed_ips_group_ip_1_text)
        # ///////////////////////////////////
        forwarding_group1 = "somewhere"
        forwarding_group2 = "google"
        forwarding_group1_text = """
            co
            global.bing.com
            xyz.com
        """
        forwarding_group2_text = """
            def.co
            =bing.com
            abc*.xyz.com
        """
        forwarding_rules = parse_forwarding_rules(forwarding_group1, forwarding_group1_text)
        forwarding_rules.extend(parse_forwarding_rules(forwarding_group2, forwarding_group2_text))
        # ///////////////////////////////////
        allowed_names = parse_allowed_names(group_default, forwarding_group1_text)
        allowed_names.extend(parse_allowed_names(group_ip_1, forwarding_group2_text))
        # ///////////////////////////////////
        blocked_names = parse_blocked_names(group_default, forwarding_group2_text)
        # noinspection SpellCheckingInspection
        cloaking_rules_text = """

=epicgames.com                                          3.211.255.75
=epicgames.com                                          3.217.242.194
=epicgames.com                                          3.224.77.1
www.epicgames.com                                       epicgames.com
xmpp-service-prod.ol.epicgames.com                      xmpp-service-prod-weighted.ol.epicgames.com
*.zendesk.com                                           104.16.53.111

        """
        cloaking_rules = parse_cloaking_rules(group_default, cloaking_rules_text)
        rules: DnsServerRules = DnsServerRules(
            allowed_ips=allowed_ips,
            allowed_names=allowed_names,
            blocked_ips=blocked_ips,
            blocked_names=blocked_names,
            cloaking_rules=cloaking_rules,
            forwarding_rules=forwarding_rules,
        )
        cls.forwarding_group1 = forwarding_group1
        cls.forwarding_group2 = forwarding_group2
        cls.group_default = group_default
        cls.group_ip_1 = group_ip_1
        db_job = TheDbJob(in_memory=True)
        cls.db_job = db_job
        db_job.init_db(rules)

    @classmethod
    def tearDownClass(cls) -> None:
        # noinspection PyUnresolvedReferences
        cls.db_job.db.close()

    def test_user_version(self):
        user_version = self.db_job.pragma_user_version()
        self.assertEqual(user_version, __pragma_user_version__)

        user_version = self.db_job.pragma_user_version(__pragma_user_version__)
        self.assertEqual(user_version, __pragma_user_version__)

        user_version = self.db_job.pragma_user_version()
        self.assertEqual(user_version, __pragma_user_version__)

    def test_allowed_ips(self):
        result = self.db_job.allowed_ips("192.168.0.100", "10.10.10.10")
        self.assertIsNone(result)

        result = self.db_job.allowed_ips(self.group_ip_1, "10.10.10.10")
        self.assertIsNotNone(result)

        result = self.db_job.allowed_ips("192.168.0.100", "10.10.10.11")
        self.assertIsNotNone(result)
        self.assertEqual(AllowedIpItem(group="default", ip="10.10.10.1[1-2]", use_glob=True), result)

    def test_allowed_names(self):
        result = self.db_job.allowed_names("192.168.0.100", "abc.co")
        self.assertEqual(AllowedNameItem(group=self.group_default, name="co", use_glob=False), result)

        result = self.db_job.allowed_names(self.group_ip_1, "abc.co")
        self.assertEqual(AllowedNameItem(group=self.group_default, name="co", use_glob=False), result)

        result = self.db_job.allowed_names(self.group_ip_1, "www.def.co")
        # self.assertIn(AllowedNameItem(group=self.group_default, name="co", use_glob=False), result)
        self.assertEqual(AllowedNameItem(group=self.group_ip_1, name="def.co", use_glob=False), result)

        result = self.db_job.allowed_names("192.168.0.100", "abcd.xyz.com")
        self.assertEqual(AllowedNameItem(group=self.group_default, name="xyz.com", use_glob=False), result)

        result = self.db_job.allowed_names(self.group_ip_1, "abcd.xyz.com")
        # self.assertIn(AllowedNameItem(group=self.group_default, name="xyz.com", use_glob=False), result)
        self.assertEqual(AllowedNameItem(group=self.group_ip_1, name="abc*.xyz.com", use_glob=True), result)

        result = self.db_job.allowed_names("192.168.0.100", "www.bing.com")
        self.assertIsNone(result)

        result = self.db_job.allowed_names("192.168.0.100", "global.bing.com")
        self.assertIsNotNone(result)

        result = self.db_job.allowed_names("192.168.0.100", "bing.com")
        self.assertIsNone(result)

        result = self.db_job.allowed_names(self.group_ip_1, "bing.com")
        self.assertIsNotNone(result)

    def test_blocked_ips(self):
        result = self.db_job.block_ips_ex(self.group_ip_1, "10.10.10.10")
        self.assertEqual(AllowedIpItem(group=self.group_ip_1, ip="10.10.10.10", use_glob=False), result)

        result = self.db_job.block_ips_ex(self.group_default, "10.10.10.10")
        self.assertEqual(BlockedIpItem(group=self.group_default, ip="10.10.10.10", use_glob=False), result)

    def test_blocked_names(self):
        result = self.db_job.block_names_ex(self.group_ip_1, "abc.co")
        self.assertEqual(AllowedNameItem(group=self.group_default, name="co", use_glob=False), result)

        result = self.db_job.block_names_ex(self.group_ip_1, "def.co")
        self.assertEqual(AllowedNameItem(group=self.group_ip_1, name="def.co", use_glob=False), result)

    # noinspection SpellCheckingInspection
    def test_cloaking_rules(self):
        result = self.db_job.cloaking_rules("www.epicgames.com")
        self.assertIn(
            CloakingItem(
                group="default", name="www.epicgames.com", record_type=CloakingItemRecordType.CNAME, mapped="epicgames.com", use_glob=False
            ),
            result,
        )

        result = self.db_job.cloaking_rules_ex("www.epicgames.com")
        self.assertEqual(len(result), 3)

        result = self.db_job.cloaking_rules_ex("xmpp-service-prod.ol.epicgames.com")
        self.assertEqual(len(result), 1)

        result = self.db_job.cloaking_rules("epicgames.com")
        self.assertEqual(len(result), 3)

        result = self.db_job.cloaking_rules("abc.epicgames.com")
        self.assertEqual(len(result), 0)

        result = self.db_job.cloaking_rules("zendesk.com")
        self.assertEqual(len(result), 0)

        result = self.db_job.cloaking_rules("www.zendesk.com")
        self.assertEqual(len(result), 1)

    def test_forwarding_rules(self):
        result = self.db_job.forwarding_rules("abc.co")
        self.assertEqual(result, ForwardingItem(group=self.forwarding_group1, name="co", use_glob=False))

        result = self.db_job.forwarding_rules("www.def.co")
        self.assertEqual(result, ForwardingItem(group=self.forwarding_group2, name="def.co", use_glob=False))

        result = self.db_job.forwarding_rules("www.bing.com")
        self.assertIsNone(result)

        result = self.db_job.forwarding_rules("global.bing.com")
        self.assertEqual(result, ForwardingItem(group=self.forwarding_group1, name="global.bing.com", use_glob=False))

        result = self.db_job.forwarding_rules("abc2.xyz.com")
        self.assertEqual(result, ForwardingItem(group=self.forwarding_group2, name="abc*.xyz.com", use_glob=True))

        result = self.db_job.forwarding_rules("a.xyz.com")
        self.assertEqual(result, ForwardingItem(group=self.forwarding_group1, name="xyz.com", use_glob=False))
