# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for Discoveries API."""

__all__ = []

from datetime import datetime
import http.client
import json
import random

from django.conf import settings
from django.core.urlresolvers import reverse
from maasserver.dbviews import register_view
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from testtools.matchers import (
    Equals,
    HasLength,
)


def timestamp_format(time):
    """Convert the specified `time` to the string we expect Pison to output."""
    if time.microsecond == 0:
        return time.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        return time.strftime(
            "%%Y-%%m-%%dT%%H:%%M:%%S.%03d" % int(time.microsecond / 1000))


def get_discoveries_uri():
    """Return a Discovery's URI on the API."""
    return reverse('discoveries_handler', args=[])


def get_discovery_uri(discovery):
    """Return a Discovery URI on the API."""
    return reverse(
        'discovery_handler', args=[discovery.discovery_id])


def get_discovery_uri_by_specifiers(specifiers):
    """Return a Discovery URI on the API."""
    return reverse(
        'discovery_handler', args=[specifiers])


def make_discoveries(count=3, interface=None):
    return [
        factory.make_Discovery(
            interface=interface, time=time,
            updated=datetime.fromtimestamp(time))
        for time in range(count)
        ]


class TestDiscoveriesAPI(APITestCase.ForUser):

    def setUp(self):
        super().setUp()
        register_view("maasserver_discovery")

    def test_handler_path(self):
        self.assertEqual(
            '/api/2.0/discovery/', get_discoveries_uri())

    def get_api_results(self, *args, **kwargs):
        uri = get_discoveries_uri()
        response = self.client.get(uri, *args, **kwargs)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        results = json.loads(response.content.decode(settings.DEFAULT_CHARSET))
        return results

    def test_read(self):
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        discoveries = make_discoveries(interface=iface)
        results = self.get_api_results()
        self.assertThat(results, HasLength(3))
        expected_ids = [discovery.discovery_id for discovery in discoveries]
        result_ids = [discovery["discovery_id"] for discovery in results]
        self.assertItemsEqual(expected_ids, result_ids)

    def test_read_sorts_by_last_seen(self):
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        make_discoveries(interface=iface)
        results = self.get_api_results()
        self.assertTrue(results[0]['last_seen'] >= results[2]['last_seen'])
        self.assertTrue(results[0]['last_seen'] >= results[1]['last_seen'])
        self.assertTrue(results[1]['last_seen'] >= results[2]['last_seen'])

    def test__by_unknown_mac(self):
        rack = factory.make_RackController()
        iface = factory.make_Interface(node=rack)
        discovery = factory.make_Discovery(interface=iface)
        results = self.get_api_results({'op': 'by_unknown_mac'})
        self.assertThat(len(results), Equals(1))
        factory.make_Interface(mac_address=discovery.mac_address)
        # Now that we have a known interface with the same MAC, the discovery
        # should disappear from this query.
        results = self.get_api_results({'op': 'by_unknown_mac'})
        self.assertThat(len(results), Equals(0))

    def test__by_unknown_ip(self):
        rack = factory.make_RackController()
        iface = factory.make_Interface(node=rack)
        discovery = factory.make_Discovery(interface=iface, ip="10.0.0.1")
        results = self.get_api_results({'op': 'by_unknown_ip'})
        self.assertThat(len(results), Equals(1))
        factory.make_StaticIPAddress(ip=discovery.ip, cidr="10.0.0.0/8")
        # Now that we have a known IP address that matches, the discovery
        # should disappear from this query.
        results = self.get_api_results({'op': 'by_unknown_ip'})
        self.assertThat(len(results), Equals(0))

    def test__by_unknown_ip_and_mac__known_ip(self):
        rack = factory.make_RackController()
        iface = factory.make_Interface(node=rack)
        discovery = factory.make_Discovery(interface=iface, ip="10.0.0.1")
        results = self.get_api_results({'op': 'by_unknown_ip_and_mac'})
        self.assertThat(len(results), Equals(1))
        factory.make_StaticIPAddress(ip=discovery.ip, cidr="10.0.0.0/8")
        # Known IP address, unexpected MAC.
        results = self.get_api_results({'op': 'by_unknown_ip_and_mac'})
        self.assertThat(len(results), Equals(0))

    def test__by_unknown_ip_and_mac__known_mac(self):
        rack = factory.make_RackController()
        iface = factory.make_Interface(node=rack)
        discovery = factory.make_Discovery(interface=iface)
        results = self.get_api_results({'op': 'by_unknown_ip_and_mac'})
        self.assertThat(len(results), Equals(1))
        # Known MAC, unknown IP.
        factory.make_Interface(mac_address=discovery.mac_address)
        results = self.get_api_results({'op': 'by_unknown_ip_and_mac'})
        self.assertThat(len(results), Equals(0))


class TestDiscoveryAPI(APITestCase.ForUser):

    def setUp(self):
        super().setUp()
        register_view("maasserver_discovery")

    def test_handler_path(self):
        discovery = factory.make_Discovery()
        self.assertEqual(
            '/api/2.0/discovery/%s/' % discovery.discovery_id,
            get_discovery_uri(discovery))

    def test_read(self):
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        discoveries = make_discoveries(interface=iface)
        discovery = discoveries[1]
        uri = get_discovery_uri(discovery)
        response = self.client.get(uri)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        result = json.loads(response.content.decode(settings.DEFAULT_CHARSET))
        # Spot check expected values in the results
        self.assertThat(
            result["resource_uri"],
            Equals(get_discovery_uri(discovery)))
        self.assertThat(
            result["observer"]["system_id"],
            Equals(rack.system_id))
        self.assertThat(
            result["observer"]["hostname"],
            Equals(rack.hostname))
        self.assertThat(
            result["observer"]["interface_name"],
            Equals(iface.name))
        self.assertThat(
            result["observer"]["interface_id"],
            Equals(iface.id))
        self.assertThat(
            result["ip"],
            Equals(discovery.ip))
        self.assertThat(
            result["mac_address"],
            Equals(discovery.mac_address))
        self.assertThat(
            result["hostname"],
            Equals(discovery.hostname))
        self.assertThat(
            result["last_seen"],
            Equals(timestamp_format(discovery.last_seen)))

    def test_read_by_specifiers(self):
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        [discovery] = make_discoveries(interface=iface, count=1)
        uri = get_discovery_uri_by_specifiers("ip:" + str(discovery.ip))
        response = self.client.get(uri)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        result = json.loads(response.content.decode(settings.DEFAULT_CHARSET))
        self.assertThat(
            result["ip"],
            Equals(discovery.ip))

    def test_read_404_when_bad_id(self):
        uri = reverse(
            'discovery_handler', args=[random.randint(10000, 20000)])
        response = self.client.get(uri)
        self.assertEqual(
            http.client.NOT_FOUND, response.status_code, response.content)

    def test_update_not_allowed(self):
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        discoveries = make_discoveries(interface=iface)
        discovery = discoveries[1]
        uri = get_discovery_uri(discovery)
        response = self.client.put(uri, {
            "ip": factory.make_ip_address(),
        })
        self.assertEqual(
            http.client.METHOD_NOT_ALLOWED, response.status_code,
            response.content)

    def test_delete_not_allowed_even_for_admin(self):
        self.become_admin()
        rack = factory.make_RackController()
        iface = rack.interface_set.first()
        discoveries = make_discoveries(interface=iface, count=3)
        discovery = discoveries[1]
        uri = get_discovery_uri(discovery)
        response = self.client.delete(uri)
        self.assertEqual(
            http.client.METHOD_NOT_ALLOWED, response.status_code,
            response.content)