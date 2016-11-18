#!/usr/bin/env python
#
# Copyright 2016 Greenqloud ehf
#
# sverrir@greenqloud.com
#
# Utility for adding Qstack network offerings
#

from __future__ import print_function

import minicloudstack

import MySQLdb

import argparse
import os

verbose = 0
BASE_ISOLATED_NO = "DefaultIsolatedNetworkOfferingWithSourceNatService"
DEFAULT_ISOLATED_NO = "DefaultIsolatedNetworkOfferingWithSourceNatServiceEgressEnabled"
DEFAULT_ISOLATED_NO_DISPLAY = "Offering for Isolated networks with Source Nat service and Egress enabled"
DEFAULT_SHARED_NO = "DefaultSharedNetworkOfferingWithSGService"
BAREMETAL_SHARED_NO = "BaremetalSharedNetworkOffering"
BAREMETAL_SHARED_NO_DISPLAY = "Baremetal offering for Shared networks"

def get_additional_bm_shared_services():
   return [{
        "service": "BaremetalPxeService",
        "provider": "BaremetalPxeProvider"
    },
    {
        "service": "SecurityGroup",
        "provider": "SecurityGroupProvider"
    },
    {
        "service": "Dhcp",
        "provider": "BaremetalDhcpProvider"
    },
    {
       "service": "UserData",
       "provider": "BaremetalUserdataProvider"
    }]


def get_additional_default_isolated_services():
    return [{
        "service": "BaremetalPxeService",
        "provider": "BaremetalPxeProvider"
    },
    {
        "service": "BaremetalSupport",
        "provider": "VirtualRouter"
    }]

def add_network_offerings(cs, mysql_conn):
    add_isolated_network_service_offering(cs, BASE_ISOLATED_NO, DEFAULT_ISOLATED_NO, DEFAULT_ISOLATED_NO_DISPLAY)
    ensure_baremetal_pxe_service(cs, mysql_conn) # adds BaremetalPxeService to EgressEnabled offerings without it
    service_provider_names_to_add = [svc["provider"] for svc in get_additional_default_isolated_services()]
    ensure_network_service_providers(cs, service_provider_names_to_add)
    add_baremetal_shared_network_offering(cs)


def get_offering(cs, offering_name):
    nos = cs.map("network offerings")
    names = {}
    for no in nos.itervalues():
        names[no.name] = no
    return names.get(offering_name)


def populate_services_and_providers(supportedservices, serviceproviderlist, add_services, base_offering=None):
    if base_offering:
        for service in base_offering.service:
            if verbose:
                print("service:")
                print("  name:", service.name)
                print("  provider:", [p.name for p in service.provider])
                if hasattr(service, "capability"):
                    print("  capability:", [c.as_dict() for c in service.capability])
            supportedservices.append(service.name)
            for provider in service.provider:
                serviceproviderlist.append({"service": service.name, "provider": provider.name})

    for service in add_services:
        if verbose:
            print("Adding service:", service["service"], service["provider"])
        supportedservices.append(service["service"])
        serviceproviderlist.append(service)


def define_new_offering(new_offering_name, new_offering_display, add_services, egress, base_offering=None, **kwargs):
    supportedservices = []
    serviceproviderlist = []
    populate_services_and_providers(supportedservices, serviceproviderlist, add_services, base_offering)

    new_dict = {}
    if base_offering:
        new_dict = base_offering.as_dict().copy()
        del new_dict["id"]
        del new_dict["service"]
        new_dict["isdefault"] = False
        new_dict["availability"] = "Optional"

    new_dict["name"] = new_offering_name
    new_dict["displaytext"] = new_offering_display
    new_dict["egressdefaultpolicy"] = egress
    new_dict["supportedservices"] = supportedservices
    new_dict["serviceproviderlist"] = serviceproviderlist
    new_dict.update(kwargs)
    return new_dict


def make_default_offering_optional(cs):
    # There can be only one Required offering, so we need to make any existing "Optional").
    required = cs.obj("list network offerings", availability="Required")
    if required:
        if verbose:
            print("Making {} Optional [{}]", required.name, required.id)
        cs.call("update network offering", id=required.id, availability="Optional")


def add_isolated_network_service_offering(cs, base_offering_name, new_offering_name, new_offering_display):
    if get_offering(cs, new_offering_name):
        if verbose:
            print("{} already in place".format(new_offering_name))
        return

    base_offering = get_offering(cs, base_offering_name)
    if not base_offering:
        print("Error: Did not find base offering: {}".format(base_offering_name))
        exit(1)

    new_offering_dict = define_new_offering(new_offering_name, new_offering_display,
        get_additional_default_isolated_services(), True, base_offering)
    new_offering = cs.obj("create network offering", **new_offering_dict)
    make_default_offering_optional(cs)

    cs.call("update network offering", id=new_offering.id, availability="Required", state="Enabled")


def add_baremetal_shared_network_offering(cs):
    if get_offering(cs, BAREMETAL_SHARED_NO):
        if verbose:
            print("{} already in place".format(new_offering_name))
        return

    new_offering_dict = define_new_offering(BAREMETAL_SHARED_NO, BAREMETAL_SHARED_NO_DISPLAY,
        get_additional_bm_shared_services(), False, base_offering=None, traffictype="Guest", guestiptype="Shared",
        specifyipranges=True, specifyvlan=True)
    offering = cs.obj("create network offering", **new_offering_dict)
    cs.call("update network offering", id=offering.id, state="Enabled")

    print("Network offering created and enabled {} ({})".format(BAREMETAL_SHARED_NO, offering.id))


def ensure_baremetal_pxe_service(cs, mysql_conn):
    """Ensure that the BaremetalPxeService is on the EgressEnabled network
       offering. This is a database call, because there is no way to
       update the services on network offerings via API command. This
       function call is in place to handle upgrading older Pottlok
       installations that don't have the service enabled on their
       network offering. True is returned if the offering is added,
       False is returned if it's already there."""
    offering = cs.obj("list network offerings", name=DEFAULT_ISOLATED_NO)

    if offering.service:
        pxe_service = "BaremetalPxeService"
        exists = [entry.name for entry in offering.service if entry.name == pxe_service]
        if exists:
            print("{} is already on offering {}.".format(pxe_service, DEFAULT_ISOLATED_NO))
            return False
        else:
            cursor = mysql_conn.cursor()
            print("{} is NOT on {}!".format(pxe_service, DEFAULT_ISOLATED_NO))
            sql = "select id from network_offerings where uuid = '%s'" % offering.id
            cursor.execute(sql)
            offering_db_id = cursor.fetchone()[0]

            sql = "insert into ntwk_offering_service_map (network_offering_id, service, provider, created)"
            sql += " values (%s, '%s', '%s', NOW())" % (offering_db_id, pxe_service, "BaremetalPxeProvider")
            cursor.execute(sql)
            mysql_conn.commit()
            print("{} now enabled on {}".format(pxe_service, DEFAULT_ISOLATED_NO))
            return True
    else:
        raise ValueError("No service entry for the offering found!")


def get_zone_dict(cs):
    """Assemble a dict of zones (zone ID -> zone dict) in the system."""
    zone_list = cs.call("list zones")
    if "zone" in zone_list:
        zone_list = minicloudstack.peel(zone_list, ".zone")
    zones = {}
    for zone in zone_list:
        zones[zone["id"]] = zone
    return zones


def get_physical_networks(cs):
    """Return a list of physical networks."""
    physical_networks = cs.call("list physical networks")
    return minicloudstack.peel(physical_networks, ".physicalnetwork")


def ensure_network_service_providers(cs, serviceproviderlist):
    """Makes sure that the network service providers being added are added
       and enabled on all applicable physical networks. The
       BaremetalDhcpProvider and BaremetalUserdataProvider should only
       be enabled in Basic zones (see CreatePhysicalNetworkCmd in CS),
       but otherwise all added services should get enabled in all
       physical networks. This method was written with enabling the
       BaremetalPxeProvider in mind. """

    print("Ensuring that {} providers are enabled on physical networks".format(serviceproviderlist))

    zones = get_zone_dict(cs)
    if not zones:
        print ("No zones found. Aborting physical network service provider setup.")
        return

    physical_networks = get_physical_networks(cs)

    for physical_network in physical_networks:
        phys_netw_id = physical_network['id']
        phys_netw_service_providers = cs.call("list network service providers", physicalnetworkid=phys_netw_id)
        if not phys_netw_service_providers:
            phys_netw_service_providers = []
        else:
            phys_netw_service_providers = minicloudstack.peel(phys_netw_service_providers, ".networkserviceprovider")
        zone = zones[physical_network["zoneid"]]

        for sp_name in serviceproviderlist:
            ensure_network_service_provider(cs, zone, phys_netw_id, phys_netw_service_providers, sp_name)


def ensure_network_service_provider(cs, zone, phys_netw_id, phys_netw_service_providers, sp_name):
    """Ensure that service provider sp_name exists and is enabled on the
       physical network with ID phys_netw_id. the phys_netw_service_providers
       list is the list of current NSPs on the physical network.
       The zone is the zone object of the physical network."""

    # BaremetalDhcpProvider and BaremetalUserdataProvider can only be
    # enabled in basic zones (see below). Likewise, VirtualRouter only
    # enables in advanced zones.
    LIMITATIONS = {"BaremetalDhcpProvider": "Basic",
                    "BaremetalUserdataProvider": "Basic",
                    "VirtualRouter": "Advanced"}

    # The if condition on this list comprehension should prevent KeyErrors.
    service_providers_on_pn = [item['name'] for item in phys_netw_service_providers
                               if item is not None and 'name' in item]

    if sp_name not in service_providers_on_pn:
        # The providers in BM_EXCEPTIONS can only be enabled in basic zones.
        if sp_name not in LIMITATIONS or LIMITATIONS[sp_name] == zone["networktype"]:
            nsp = cs.obj("add network service provider", physicalnetworkid=phys_netw_id, name=sp_name)
            cs.call("update network service provider", id=nsp.id, state="Enabled")
            print("Added NSP {} to physical network {} (zone = {})".format(sp_name, phys_netw_id, zone["name"]))
    else:
        service_provider = next(item for item in phys_netw_service_providers if item is not None and 'name' in item
            and item['name'] == sp_name)
        if service_provider['state'] != 'Enabled':
            cs.call("update network service provider", id=service_provider['id'], state="Enabled")
            print("Enabled NSP {} on physical network {} (zone = {})".format(sp_name, phys_netw_id, zone["name"]))
        else:
            print("{} is already added and enabled on physical network {}".format(sp_name, phys_netw_id))


def main():
    global verbose

    parser = argparse.ArgumentParser("Adds default Qstack network offerings if they have not been installed")

    parser.add_argument("-v", "--verbose", action="count", help="Increase output verbosity")

    # mysql connection info
    host = os.environ.get("MYSQL_HOST", "")
    user = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PW", "")
    db = os.environ.get("MYSQL_DB", "")

    mysql = parser.add_argument_group("MySQL", "MySQL connection info")
    mysql.add_argument("--host", default=host, required=(len(host) == 0), help="MySQL hostname")
    mysql.add_argument("--user", default=user, required=(len(user) == 0), help="MySQL username")
    mysql.add_argument("--password", default=password, required=(len(host) == 0), help="MySQL password")
    mysql.add_argument("--db", default=db, required=(len(db) == 0), help="MySQL database")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()

    verbose = arguments.verbose
    minicloudstack.set_verbosity(arguments.verbose)

    cs = minicloudstack.MiniCloudStack(arguments)
    mysql_conn = MySQLdb.connect(arguments.host, arguments.user, arguments.password, arguments.db)
    add_network_offerings(cs, mysql_conn)
    mysql_conn.close()


if __name__ == "__main__":
    main()
