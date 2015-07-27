# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for all forms that are used with `RAID`."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

import random
from uuid import uuid4

from maasserver.enum import (
    FILESYSTEM_GROUP_TYPE,
    FILESYSTEM_TYPE,
)
from maasserver.forms import (
    CreateRaidForm,
    UpdateRaidForm,
)
from maasserver.models.filesystemgroup import RAID
from maasserver.models.partitiontable import INITIAL_PARTITION_OFFSET
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase


def _make_interesting_RAID(
        node, level=FILESYSTEM_GROUP_TYPE.RAID_6, num_devices=10,
        num_partitions=10, num_spare_devices=2, num_spare_partitions=2):
    """Returns a RAID that is interesting for our tests."""
    size = 1000 ** 4  # A Terabyte.
    block_devices = [factory.make_BlockDevice(node=node, size=size)
                     for _ in range(num_devices)]
    partitions = [factory.make_Partition(node=node, block_device_size=size)
                  for _ in range(num_partitions)]
    spare_devices = [factory.make_BlockDevice(node=node, size=size)
                     for _ in range(num_spare_devices)]
    spare_partitions = [
        factory.make_Partition(node=node, block_device_size=size)
        for _ in range(num_spare_partitions)
    ]

    return RAID.objects.create_raid(
        name='md%d' % random.randint(1, 1000),
        level=level,
        uuid=uuid4(),
        block_devices=block_devices,
        partitions=partitions,
        spare_devices=spare_devices,
        spare_partitions=spare_partitions
    )


class TestCreateRaidForm(MAASServerTestCase):

    def test_requires_fields(self):
        node = factory.make_Node()
        form = CreateRaidForm(node=node, data={})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertDictContainsSubset(
            {
                'level': ['This field is required.'],
            },
            form.errors)

    def test_choices_are_being_populated_correctly(self):
        node = factory.make_Node()
        bds = [
            factory.make_PhysicalBlockDevice(node=node, size=10 * 1000 ** 4)
            for _ in range(10)
        ]
        for bd in bds[5:]:
            factory.make_PartitionTable(block_device=bd)
        block_devices = [
            bd.id
            for bd in bds
            if bd.get_partitiontable() is None
        ]
        partitions = [
            bd.get_partitiontable().add_partition().id
            for bd in bds[5:]
        ]
        form = CreateRaidForm(node=node, data={})
        self.assertItemsEqual(
            block_devices,
            [k for (k, v) in form.fields['block_devices'].choices])
        self.assertItemsEqual(
            partitions,
            [k for (k, v) in form.fields['partitions'].choices])
        self.assertItemsEqual(
            block_devices,
            [k for (k, v) in form.fields['spare_devices'].choices])
        self.assertItemsEqual(
            partitions,
            [k for (k, v) in form.fields['spare_partitions'].choices])

    def test_raid_creation_on_save(self):
        node = factory.make_Node()
        device_size = 10 * 1000 ** 4
        bds = [
            factory.make_PhysicalBlockDevice(node=node, size=device_size)
            for _ in range(10)
        ]
        for bd in bds[5:]:
            factory.make_PartitionTable(block_device=bd)
        block_devices = [
            bd.id
            for bd in bds
            if bd.get_partitiontable() is None
        ]
        partitions = [
            bd.get_partitiontable().add_partition().id
            for bd in bds[5:]
        ]
        # Partition size will be smaller than the disk, because of overhead.
        partition_size = device_size - INITIAL_PARTITION_OFFSET
        form = CreateRaidForm(node=node, data={
            'name': 'md1',
            'level': FILESYSTEM_GROUP_TYPE.RAID_6,
            'block_devices': block_devices,
            'partitions': partitions,
        })
        self.assertTrue(form.is_valid(), form.errors)
        raid = form.save()
        self.assertEqual('md1', raid.name)
        self.assertEqual(8 * partition_size, raid.get_size())
        self.assertEqual(FILESYSTEM_GROUP_TYPE.RAID_6, raid.group_type)
        self.assertItemsEqual(
            block_devices,
            [fs.block_device.id
             for fs in raid.filesystems.exclude(block_device=None)])
        self.assertItemsEqual(
            partitions,
            [fs.partition.id
             for fs in raid.filesystems.exclude(partition=None)])

    def test_raid_creation_without_storage_fails(self):
        node = factory.make_Node()
        for level in [
                FILESYSTEM_GROUP_TYPE.RAID_0,
                FILESYSTEM_GROUP_TYPE.RAID_1,
                FILESYSTEM_GROUP_TYPE.RAID_4,
                FILESYSTEM_GROUP_TYPE.RAID_5,
                FILESYSTEM_GROUP_TYPE.RAID_6,
        ]:
            form = CreateRaidForm(node=node, data={
                'name': 'md1',
                'level': level,
                'block_devices': [],
                'partitions': [],
            })
            self.assertFalse(form.is_valid())
            self.assertDictContainsSubset(
                {
                    u'__all__': ['At least one block device or partition must '
                                 'be added to the array.']
                },
                form.errors)


class TestUpdateRaidForm(MAASServerTestCase):

    # Add devices and partitions
    def test_add_valid_blockdevice(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new blockdevices to the node.
        bd_ids = [factory.make_BlockDevice(node=raid.get_node()).id
                  for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_block_devices': bd_ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_valid_partition(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new partitions to the node.
        part_ids = [factory.make_Partition(node=raid.get_node()).id
                    for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_partitions': part_ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_valid_spare_device(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new blockdevices to the node.
        bd_ids = [factory.make_BlockDevice(node=raid.get_node()).id
                  for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_spare_devices': bd_ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_valid_spare_partition(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new partitions to the node.
        part_ids = [factory.make_Partition(node=raid.get_node()).id
                    for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_spare_partitions': part_ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_invalid_blockdevice_fails(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new blockdevices to other nodes.
        bd_ids = [factory.make_BlockDevice().id for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_block_devices': bd_ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('add_block_devices', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['add_block_devices'][0])

    def test_add_invalid_spare_blockdevice_fails(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new blockdevices to other nodes.
        bd_ids = [factory.make_BlockDevice().id for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_spare_devices': bd_ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('add_spare_devices', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['add_spare_devices'][0])

    def test_add_invalid_partition_fails(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new partitions to other nodes.
        part_ids = [factory.make_Partition().id for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_partitions': part_ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('add_partitions', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['add_partitions'][0])

    def test_add_invalid_spare_partition_fails(self):
        raid = factory.make_FilesystemGroup(
            group_type=FILESYSTEM_GROUP_TYPE.RAID_6)
        # Add 5 new partitions to other nodes.
        part_ids = [factory.make_Partition().id for _ in range(5)]
        form = UpdateRaidForm(raid, data={'add_spare_partitions': part_ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('add_spare_partitions', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['add_spare_partitions'][0])

    # Removal tests

    def test_remove_valid_blockdevice(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [
            fs.block_device.id
            for fs in raid.filesystems.filter(
                fstype=FILESYSTEM_TYPE.RAID).exclude(block_device=None)[:2]
        ]  # Select 2 items for removal
        form = UpdateRaidForm(raid, data={'remove_block_devices': ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_remove_valid_partition(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [
            fs.partition.id
            for fs in raid.filesystems.filter(
                fstype=FILESYSTEM_TYPE.RAID).exclude(partition=None)[:2]
        ]  # Select 2 items for removal
        form = UpdateRaidForm(raid, data={'remove_partitions': ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_remove_valid_spare_device(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [
            fs.block_device.id
            for fs in raid.filesystems.filter(
                fstype=FILESYSTEM_TYPE.RAID_SPARE)
            .exclude(block_device=None)[:2]
        ]  # Select 2 items for removal
        form = UpdateRaidForm(raid, data={'remove_block_devices': ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_remove_valid_spare_partition(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [
            fs.partition.id
            for fs in raid.filesystems.filter(
                fstype=FILESYSTEM_TYPE.RAID_SPARE).exclude(partition=None)[:2]
        ]  # Select 2 items for removal
        form = UpdateRaidForm(raid, data={'remove_partitions': ids})
        self.assertTrue(form.is_valid(), form.errors)

    def test_remove_invalid_blockdevice_fails(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [factory.make_BlockDevice().id for _ in range(2)]
        form = UpdateRaidForm(raid, data={'remove_block_devices': ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('remove_block_devices', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['remove_block_devices'][0])

    def test_remove_invalid_spare_blockdevice_fails(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [factory.make_BlockDevice().id for _ in range(2)]
        form = UpdateRaidForm(raid, data={'remove_spare_devices': ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('remove_spare_devices', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['remove_spare_devices'][0])

    def test_remove_invalid_partition_fails(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [factory.make_Partition().id for _ in range(2)]
        form = UpdateRaidForm(raid, data={'remove_partitions': ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('remove_partitions', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['remove_partitions'][0])

    def test_remove_invalid_spare_partition_fails(self):
        raid = _make_interesting_RAID(node=factory.make_Node())
        ids = [factory.make_Partition().id for _ in range(2)]
        form = UpdateRaidForm(raid, data={'remove_spare_partitions': ids})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertIn('remove_spare_partitions', form.errors)
        self.assertIn(
            'is not one of the available choices.',
            form.errors['remove_spare_partitions'][0])