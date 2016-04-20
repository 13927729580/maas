# Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `maasserver.websockets.handlers.fabric`"""

__all__ = []

from maasserver.models.fabric import Fabric
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.websockets.handlers.fabric import FabricHandler
from maasserver.websockets.handlers.timestampedmodel import dehydrate_datetime


class TestFabricHandler(MAASServerTestCase):

    def dehydrate_fabric(self, fabric):
        data = {
            "id": fabric.id,
            "name": fabric.get_name(),
            "class_type": fabric.class_type,
            "updated": dehydrate_datetime(fabric.updated),
            "created": dehydrate_datetime(fabric.created),
            "vlan_ids": sorted([
                vlan.id
                for vlan in fabric.vlan_set.all()
            ]),
        }
        return data

    def test_get(self):
        user = factory.make_User()
        handler = FabricHandler(user, {})
        fabric = factory.make_Fabric()
        vlan = fabric.get_default_vlan()
        for _ in range(3):
            node = factory.make_Node(interface=True)
            interface = node.get_boot_interface()
            interface.vlan = vlan
            interface.save()
        self.assertEqual(
            self.dehydrate_fabric(fabric),
            handler.get({"id": fabric.id}))

    def test_get_default_vlan_is_first(self):
        user = factory.make_User()
        handler = FabricHandler(user, {})
        fabric = factory.make_Fabric()
        default_vlan = fabric.get_default_vlan()
        tagged_vlan_ids = [
            factory.make_VLAN(fabric=fabric).id
            for _ in range(3)
        ]
        observed = handler.get({"id": fabric.id})
        self.assertEqual(
            [default_vlan.id] + tagged_vlan_ids,
            observed["vlan_ids"])

    def test_list(self):
        user = factory.make_User()
        handler = FabricHandler(user, {})
        factory.make_Fabric()
        expected_fabrics = [
            self.dehydrate_fabric(fabric)
            for fabric in Fabric.objects.all()
            ]
        self.assertItemsEqual(
            expected_fabrics,
            handler.list({}))
