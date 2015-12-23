# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `rpc.leases`."""

__all__ = []

from datetime import datetime
import random
import time

from maasserver.enum import (
    INTERFACE_TYPE,
    IPADDRESS_FAMILY,
    IPADDRESS_TYPE,
    NODEGROUP_STATUS,
    NODEGROUPINTERFACE_MANAGEMENT,
)
from maasserver.models.interface import UnknownInterface
from maasserver.models.staticipaddress import StaticIPAddress
from maasserver.rpc.leases import (
    LeaseUpdateError,
    update_lease,
)
from maasserver.testing.factory import factory
from maasserver.testing.orm import reload_object
from maasserver.testing.testcase import MAASServerTestCase
from netaddr import IPAddress
from provisioningserver.rpc.exceptions import NoSuchCluster
from testtools.matchers import MatchesStructure


class TestUpdateLease(MAASServerTestCase):

    def make_kwargs(
            self, cluster_uuid, action=None, mac=None, ip=None, timestamp=None,
            lease_time=None, hostname=None, subnet=None):
        if action is None:
            action = random.choice(["commit", "expiry", "release"])
        if mac is None:
            mac = factory.make_mac_address()
        if ip is None:
            if subnet is not None:
                ip = factory.pick_ip_in_network(subnet.get_ipnetwork())
            else:
                ip = factory.make_ip_address()
        if timestamp is None:
            timestamp = int(time.time())
        if action == "commit":
            if lease_time is None:
                lease_time = random.randint(30, 1000)
            if hostname is None:
                hostname = factory.make_name("host")
        ip_family = "ipv4"
        if IPAddress(ip).version == IPADDRESS_FAMILY.IPv6:
            ip_family = "ipv6"
        return {
            "cluster_uuid": cluster_uuid,
            "action": action,
            "mac": mac,
            "ip": ip,
            "ip_family": ip_family,
            "timestamp": timestamp,
            "lease_time": lease_time,
            "hostname": hostname,
        }

    def make_managed_subnet(self):
        nodegroup = factory.make_NodeGroup(status=NODEGROUP_STATUS.ENABLED)
        subnet = factory.make_Subnet()
        ngi = factory.make_NodeGroupInterface(
            nodegroup=nodegroup, subnet=subnet,
            management=NODEGROUPINTERFACE_MANAGEMENT.DHCP)
        return nodegroup, subnet, ngi

    def test_raises_NoSuchCluster(self):
        uuid = factory.make_UUID()
        kwargs = self.make_kwargs(uuid)
        self.assertRaises(NoSuchCluster, update_lease, **kwargs)

    def test_raises_LeaseUpdateError_for_unknown_action(self):
        nodegroup = factory.make_NodeGroup()
        action = factory.make_name("action")
        kwargs = self.make_kwargs(nodegroup.uuid, action=action)
        error = self.assertRaises(LeaseUpdateError, update_lease, **kwargs)
        self.assertEquals(
            "Unknown lease action: %s" % action, str(error))

    def test_raises_LeaseUpdateError_for_no_subnet(self):
        nodegroup = factory.make_NodeGroup()
        kwargs = self.make_kwargs(nodegroup.uuid)
        error = self.assertRaises(LeaseUpdateError, update_lease, **kwargs)
        self.assertEquals(
            "No subnet exists for: %s" % kwargs["ip"], str(error))

    def test_raises_LeaseUpdateError_for_ipv4_mismatch(self):
        nodegroup = factory.make_NodeGroup()
        ipv6_network = factory.make_ipv6_network()
        subnet = factory.make_Subnet(cidr=str(ipv6_network.cidr))
        factory.make_NodeGroupInterface(
            nodegroup=nodegroup, subnet=subnet)
        kwargs = self.make_kwargs(nodegroup.uuid, subnet=subnet)
        kwargs["ip_family"] = "ipv4"
        error = self.assertRaises(LeaseUpdateError, update_lease, **kwargs)
        self.assertEquals(
            "Family for the subnet does not match. Expected: ipv4", str(error))

    def test_raises_LeaseUpdateError_for_ipv6_mismatch(self):
        nodegroup = factory.make_NodeGroup()
        ipv4_network = factory.make_ipv4_network()
        subnet = factory.make_Subnet(cidr=str(ipv4_network.cidr))
        factory.make_NodeGroupInterface(
            nodegroup=nodegroup, subnet=subnet)
        kwargs = self.make_kwargs(nodegroup.uuid, subnet=subnet)
        kwargs["ip_family"] = "ipv6"
        error = self.assertRaises(LeaseUpdateError, update_lease, **kwargs)
        self.assertEquals(
            "Family for the subnet does not match. Expected: ipv6", str(error))

    def test_does_nothing_if_not_in_dyanmic_range(self):
        nodegroup, _, ngi = self.make_managed_subnet()
        ip = str(IPAddress(ngi.get_static_ip_range()[0]))
        kwargs = self.make_kwargs(nodegroup.uuid, ip=ip)
        update_lease(**kwargs)
        self.assertIsNone(
            StaticIPAddress.objects.filter(
                alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=ip).first())

    def test_does_nothing_if_expiry_for_unknown_mac(self):
        nodegroup, _, ngi = self.make_managed_subnet()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(nodegroup.uuid, action="expiry", ip=ip)
        update_lease(**kwargs)
        self.assertIsNone(
            StaticIPAddress.objects.filter(
                alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=ip).first())

    def test_does_nothing_if_release_for_unknown_mac(self):
        nodegroup, _, ngi = self.make_managed_subnet()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(nodegroup.uuid, action="release", ip=ip)
        update_lease(**kwargs)
        self.assertIsNone(
            StaticIPAddress.objects.filter(
                alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=ip).first())

    def test_creates_lease_for_unknown_interface(self):
        nodegroup, subnet, ngi = self.make_managed_subnet()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(nodegroup.uuid, action="commit", ip=ip)
        update_lease(**kwargs)
        unknown_interface = UnknownInterface.objects.filter(
            mac_address=kwargs["mac"]).first()
        self.assertIsNotNone(unknown_interface)
        self.assertEquals(subnet.vlan, unknown_interface.vlan)
        sip = unknown_interface.ip_addresses.first()
        self.assertIsNotNone(sip)
        self.assertThat(sip, MatchesStructure.byEquality(
            alloc_type=IPADDRESS_TYPE.DISCOVERED,
            ip=ip,
            subnet=subnet,
            lease_time=kwargs["lease_time"],
            hostname=kwargs["hostname"],
            created=datetime.fromtimestamp(kwargs["timestamp"]),
            updated=datetime.fromtimestamp(kwargs["timestamp"]),
        ))

    def test_creates_ignores_none_hostname(self):
        nodegroup, subnet, ngi = self.make_managed_subnet()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(
            nodegroup.uuid, action="commit", ip=ip, hostname="(none)")
        update_lease(**kwargs)
        unknown_interface = UnknownInterface.objects.filter(
            mac_address=kwargs["mac"]).first()
        self.assertIsNotNone(unknown_interface)
        self.assertEquals(subnet.vlan, unknown_interface.vlan)
        sip = unknown_interface.ip_addresses.first()
        self.assertIsNotNone(sip)
        self.assertThat(sip, MatchesStructure.byEquality(
            alloc_type=IPADDRESS_TYPE.DISCOVERED,
            ip=ip,
            subnet=subnet,
            lease_time=kwargs["lease_time"],
            hostname=None,
            created=datetime.fromtimestamp(kwargs["timestamp"]),
            updated=datetime.fromtimestamp(kwargs["timestamp"]),
        ))

    def test_creates_lease_for_physical_interface(self):
        node = factory.make_Node_with_Interface_on_Subnet()
        boot_interface = node.get_boot_interface()
        ip_address = boot_interface.ip_addresses.first()
        subnet = ip_address.subnet
        ngi = subnet.nodegroupinterface_set.first()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(
            ngi.nodegroup.uuid, action="commit",
            mac=boot_interface.mac_address, ip=ip)
        update_lease(**kwargs)

        sip = StaticIPAddress.objects.filter(
            alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=ip).first()
        self.assertThat(sip, MatchesStructure.byEquality(
            alloc_type=IPADDRESS_TYPE.DISCOVERED,
            ip=ip,
            subnet=subnet,
            lease_time=kwargs["lease_time"],
            hostname=kwargs["hostname"],
            created=datetime.fromtimestamp(kwargs["timestamp"]),
            updated=datetime.fromtimestamp(kwargs["timestamp"]),
        ))
        self.assertItemsEqual(
            [boot_interface.id],
            sip.interface_set.values_list("id", flat=True))
        self.assertEqual(
            1,
            StaticIPAddress.objects.filter_by_ip_family(
                subnet.get_ipnetwork().version).filter(
                alloc_type=IPADDRESS_TYPE.DISCOVERED,
                interface=boot_interface).count(),
            "Interface should only have one DISCOVERED IP address.")

    def test_creates_lease_for_physical_interface_keeps_other_ip_family(self):
        node = factory.make_Node_with_Interface_on_Subnet()
        boot_interface = node.get_boot_interface()
        ip_address = boot_interface.ip_addresses.first()
        subnet = ip_address.subnet
        ngi = subnet.nodegroupinterface_set.first()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(
            ngi.nodegroup.uuid, action="commit",
            mac=boot_interface.mac_address, ip=ip)

        # Make DISCOVERED in the other address family to make sure it is
        # not removed.
        network = subnet.get_ipnetwork()
        if network.version == IPADDRESS_FAMILY.IPv4:
            other_network = factory.make_ipv6_network()
        else:
            other_network = factory.make_ipv4_network()
        other_subnet = factory.make_Subnet(cidr=str(other_network.cidr))
        other_ip = factory.make_StaticIPAddress(
            alloc_type=IPADDRESS_TYPE.DISCOVERED, ip="", subnet=other_subnet,
            interface=boot_interface)

        update_lease(**kwargs)
        self.assertIsNotNone(
            reload_object(other_ip),
            "DISCOVERED IP address from the other address family should not "
            "have been deleted.")

    def test_creates_lease_for_bond_interface(self):
        node = factory.make_Node_with_Interface_on_Subnet()
        boot_interface = node.get_boot_interface()
        ip_address = boot_interface.ip_addresses.first()
        subnet = ip_address.subnet
        ngi = subnet.nodegroupinterface_set.first()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))

        bond_interface = factory.make_Interface(
            INTERFACE_TYPE.BOND, mac_address=boot_interface.mac_address,
            parents=[boot_interface])

        kwargs = self.make_kwargs(
            ngi.nodegroup.uuid, action="commit",
            mac=bond_interface.mac_address, ip=ip)
        update_lease(**kwargs)

        sip = StaticIPAddress.objects.filter(
            alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=ip).first()
        self.assertThat(sip, MatchesStructure.byEquality(
            alloc_type=IPADDRESS_TYPE.DISCOVERED,
            ip=ip,
            subnet=subnet,
            lease_time=kwargs["lease_time"],
            hostname=kwargs["hostname"],
            created=datetime.fromtimestamp(kwargs["timestamp"]),
            updated=datetime.fromtimestamp(kwargs["timestamp"]),
        ))
        self.assertItemsEqual(
            [boot_interface.id, bond_interface.id],
            sip.interface_set.values_list("id", flat=True))

    def test_release_removes_lease_keeps_discovered_subnet(self):
        node = factory.make_Node_with_Interface_on_Subnet()
        boot_interface = node.get_boot_interface()
        ip_address = boot_interface.ip_addresses.first()
        subnet = ip_address.subnet
        ngi = subnet.nodegroupinterface_set.first()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(
            ngi.nodegroup.uuid, action="release",
            mac=boot_interface.mac_address, ip=ip)
        update_lease(**kwargs)

        sip = StaticIPAddress.objects.filter(
            alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=None,
            subnet=subnet, interface=boot_interface).first()
        self.assertIsNotNone(
            sip,
            "DISCOVERED IP address shold have been created without an "
            "IP address.")
        self.assertItemsEqual(
            [boot_interface.id],
            sip.interface_set.values_list("id", flat=True))

    def test_expiry_removes_lease_keeps_discovered_subnet(self):
        node = factory.make_Node_with_Interface_on_Subnet()
        boot_interface = node.get_boot_interface()
        ip_address = boot_interface.ip_addresses.first()
        subnet = ip_address.subnet
        ngi = subnet.nodegroupinterface_set.first()
        ip = str(IPAddress(ngi.get_dynamic_ip_range()[0]))
        kwargs = self.make_kwargs(
            ngi.nodegroup.uuid, action="expiry",
            mac=boot_interface.mac_address, ip=ip)
        update_lease(**kwargs)

        sip = StaticIPAddress.objects.filter(
            alloc_type=IPADDRESS_TYPE.DISCOVERED, ip=None,
            subnet=subnet, interface=boot_interface).first()
        self.assertIsNotNone(
            sip,
            "DISCOVERED IP address shold have been created without an "
            "IP address.")
        self.assertItemsEqual(
            [boot_interface.id],
            sip.interface_set.values_list("id", flat=True))