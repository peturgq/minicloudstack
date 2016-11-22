import logging
import minicloudstack

import unittest


class TestMiniCloudStack(unittest.TestCase):
    def test_ipaddress(self):
        self.check_ip("0.0.0.0")
        self.check_ip("255.255.255.255")
        self.check_ip("192.168.101.50")
        self.check_ip("192.168.101.51")
        self.check_ip("1.2.3.4")
        self.check_ip("128.0.0.1")

    def check_ip(self, ipaddr):
        ip = minicloudstack.IpAddress(ipaddr)
        self.assertEquals(ipaddr, ip.dotted())
        self.assertEquals(ipaddr, ip.new_adding(0).dotted())

        if ipaddr != "255.255.255.255":
            self.assertEquals(ipaddr, ip.new_adding(1).new_adding(-1).dotted())
        if ipaddr != "0.0.0.0":
            self.assertEquals(ipaddr, ip.new_adding(-1).new_adding(1).dotted())

        self.check_all(ip, 0)
        self.check_all(ip, 8)
        self.check_all(ip, 16)
        self.check_all(ip, 24)
        self.check_all(ip, 32)
        self.check_all(ip, 22)
        self.check_all(ip, 31)

    def check_all(self, ip, significant_bits):
        firstip = lastip = False
        m = minicloudstack.IpCidr(ip.dotted() + "/" + str(significant_bits))
        self.assertEquals(ip.dotted(), m.ip().dotted())
        if firstip:
            self.assertEquals(ip, m.firstip().dotted())
        if lastip:
            self.assertEquals(ip, m.lastip().dotted())

        self.assertGreaterEqual(ip.integer(), m.firstip().integer())
        self.assertLessEqual(ip.integer(), m.lastip().integer())

        logging.debug("cidr {}: ip {}".format(m.cidr(), m.ip().dotted()))
        logging.debug(" from {}-{}".format(m.firstip().dotted(), m.lastip().dotted()))
        logging.debug(" mask {}".format(m.netmask().dotted()))

    def test_ip_compare(self):
        ip1 = minicloudstack.IpAddress("10.1.1.1")
        ip2 = minicloudstack.IpAddress("10.1.1.2")
        self.assertTrue(ip2.greater_than(ip1))
        self.assertFalse(ip2.greater_than(ip2))
        self.assertFalse(ip1.greater_than(ip2))
