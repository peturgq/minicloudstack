#!/usr/bin/python
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import print_function
import argparse
import re

# Python 2 vs 3
try:
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from urlparse import urlparse, parse_qs

from . import mcs as minicloudstack
from . import networkoffering
from . import addhost
from . import baremetal

RE_VLAN_RANGE = re.compile("^([0-9]{1,4})-([0-9]{1,4})$")


def enable_networkserviceproviders(cs, pn, providers, update):
    nsps = cs.map("network service providers", physicalnetworkid=pn.id)
    for provider in providers:
        nsp = None
        for find_nsp in nsps.itervalues():
            if find_nsp.name == provider:
                if minicloudstack.get_verbosity():
                    print("Enabling service provider {} for physical network {}".format(find_nsp.name, pn.id))
                nsp = find_nsp
                break

        if not nsp and provider == "VirtualRouterSG":
            # "Gateway",
            services = ["Vpn", "Dhcp", "Dns", "Firewall", "Lb",
                        "SourceNat", "StaticNat", "PortForwarding", "UserData", "SecurityGroup"]
            nsp = cs.obj(
                    "add network service provider",
                    name=provider,
                    physicalnetworkid=pn.id,
                    servicelist=services,
            )
        elif not nsp:
            print("Warning: Failed to enable service provider {} on physical network {}".format(provider, pn.id))
            continue

        if nsp.state == "Enabled":
            if minicloudstack.get_verbosity():
                print("Network service provider {} already enabled".format(provider))
            continue

        if minicloudstack.get_verbosity():
            print("Enabling network service provider {}".format(provider))

        if nsp.name in ["VirtualRouter", "VpcVirtualRouter", "VirtualRouterSG"]:
            vre = minicloudstack.obj_if_exists(cs, "virtual router elements", nspid=nsp.id)
            if not vre:
                print("Creating virtual router element {} not found for nspid={}".format(provider, nsp.id))
                vre = cs.obj("create virtual router element", nspid=nsp.id)

            cs.obj("configure virtual router element", id=vre.id, enabled=True)
        elif nsp.name == "InternalLbVm":
            lbe = minicloudstack.obj_if_exists(cs, "internal load balancer elements", nspid=nsp.id)
            if not lbe:
                print("Warning: internal load balancer element not found for nspid={}".format(nsp.id))
                continue
            cs.obj("configure internal load balancer element", id=lbe.id, enabled=True)
        else:
            print("Warning: Unsupported network service provider '{}'".format(nsp.name))

        # Enable the service provider itself.
        cs.call("update network service provider", id=nsp.id, state="Enabled")


def add_traffictype(cs, pnid, attrs, update):
    if update:
        tts = cs.map("traffic types", physicalnetworkid=pnid)
        for tt in tts.itervalues():
            match = True
            for k, v in attrs.items():
                if hasattr(tt, k):
                    if v != getattr(tt, k):
                        match = False
                        break
            if match:
                return
    if minicloudstack.get_verbosity():
        print("Adding traffictype to '{}': {}".format(pnid, attrs))
    cs.obj("add traffic type", physicalnetworkid=pnid, **attrs)


def create_traffictype(traffictype, hypervisor, vlan=None):
    if hypervisor == "vmware":
        if vlan:
            label = "vSwitch0,{}".format(vlan)
        else:
            label = "vSwitch0"
        return {
            "vmwarenetworklabel": label,
            "traffictype": traffictype,
        }
    elif hypervisor == "hyperv":
        label = "switch0"
        return {
            "hypervnetworklabel": label,
            "traffictype": traffictype,
        }
    else:
        return {
            "kvmnetworklabel": "cloudbr0",
            "traffictype": traffictype
        }


def create_physicalnetwork(cs, zone, pn, name, hyperv, adv_netw, enable_public, enable_non_public, mgmt_vlan, public_vlan, guest_vlan, update):
    if not pn:
        additional = {}
        if adv_netw and guest_vlan:
            additional = dict(
                    vlan=guest_vlan
            )

        if zone.networktype == "Advanced":
            broadcast = "Zone"
        else:
            broadcast = "Pod"

        pn = cs.obj(
                "create physical network",
                zoneid=zone.id,
                name=name,
                broadcastdomainrange=broadcast,
                **additional
        )
        print("Physical network created {} ({})".format(pn.name, pn.id))

    service_providers = []
    add_virtual_router = True

    if enable_public:
        add_traffictype(cs, pn.id, create_traffictype("Public", hyperv, vlan=public_vlan), update)

    if enable_non_public:
        add_traffictype(cs, pn.id, create_traffictype("Management", hyperv, vlan=mgmt_vlan), update)
        add_traffictype(cs, pn.id, create_traffictype("Storage", hyperv, vlan=mgmt_vlan), update)
        add_traffictype(cs, pn.id, create_traffictype("Guest", hyperv), update)

        if adv_netw:
            cs_major, cs_minor = cs.version()
            if int(cs_major) == 4 and int(cs_minor) == 2:
                service_providers.extend(["InternalLbVm", "VpcVirtualRouter", "VirtualRouterSG"])
            else:
                service_providers.extend(["InternalLbVm", "VpcVirtualRouter"])
            service_providers.append("BaremetalPxeProvider")
        else:
            service_providers.append("SecurityGroupProvider")
            if hyperv == "baremetal":
                add_virtual_router = False
                service_providers.extend(["BaremetalDhcpProvider", "BaremetalUserdataProvider"])
                service_providers.append("BaremetalPxeProvider")

    if add_virtual_router:
        service_providers.append("VirtualRouter")

    enable_networkserviceproviders(cs, pn, service_providers, update)

    if pn.state != "Enabled":
        cs.call("update physical network", id=pn.id, state="Enabled")

    return pn


def create_physicalnetworks(cs, zone, hyperv, adv_netw, mgmt_vlan, public_vlan, guest_vlan, update):
    pns = cs.map("physical networks", zoneid=zone.id)
    pn1 = pn2 = None
    if len(pns.keys()) and update:
        if len(pns.keys()) == 2 and zone.networktype == "Advanced":
            key1, pn1 = pns.popitem()
            key2, pn2 = pns.popitem()

            # Order networks correctly.
            if hasattr(pn1, "vlan"):
                tmp = pn2
                pn2 = pn1
                pn1 = tmp

            if minicloudstack.get_verbosity():
                print("Found existing objects '{}' with ids '{}' and '{}".format(type, key1, key2))
        elif len(pns.keys()) == 1:
            key1, pn1 = pns.popitem()
        else:
            print("Warning: too many physical networks already!")
            return

    if adv_netw and hyperv == "kvm":
        pu = create_physicalnetwork(cs, zone, pn1, zone.name + "-public", hyperv, adv_netw,
                                    True, False, "", "", "", update)

        pr = create_physicalnetwork(cs, zone, pn2, zone.name + "-guest", hyperv, adv_netw,
                                    False, True, mgmt_vlan, public_vlan, guest_vlan, update)
    else:
        pu = create_physicalnetwork(cs, zone, pn1, zone.name + "-physical", hyperv, adv_netw,
                                    True, True, mgmt_vlan, public_vlan, guest_vlan, update)
        pr = None

    return pu, pr


def create_network(cs, zone, pn, name, hyperv, update):
    network = None
    if update:
        network = minicloudstack.obj_if_exists(cs, "networks", zoneid=zone.id)
    if not network:
        # find correct network offering
        if hyperv == "baremetal":
            offering_name = networkoffering.BAREMETAL_SHARED_NO
        else:
            offering_name = networkoffering.DEFAULT_SHARED_NO
        try:
            network_offering = cs.obj("list network offerings", name=offering_name)
        except:
            networkoffering.add_network_offerings(cs)
            network_offering = cs.obj("list network offerings", name=offering_name)
        if minicloudstack.get_verbosity():
            print("Found network offering {} [{}]".format(offering_name, network_offering.id))

        network = cs.obj(
                "create network",
                zoneid=zone.id,
                physicalnetworkid=pn.id,
                networkofferingid=network_offering.id,
                name=name,
                displaytext=name,
                vlan="untagged",
        )

        print("Network created {} ({})".format(network.name, network.id))
    return network


def create_vlaniprange(cs, zone, pod, gateway, pubnet, public_vlan, vmpublic_startip, vmpublic_endip, update):
    vlaniprange = None
    if update:
        vlaniprange = minicloudstack.obj_if_exists(cs, "vlan ip ranges", zoneid=zone.id)

    if not vlaniprange:
        if zone.networktype == "Advanced":
            additional = dict(
                    forvirtualnetwork=True,
            )
        else:
            additional = dict(
                    forvirtualnetwork=False,
                    podid=pod.id
            )

        vlaniprange = cs.obj(
                "create vlan ip range",
                vlan=public_vlan,
                gateway=gateway.dotted(),
                zoneid=zone.id,
                netmask=pubnet.netmask().dotted(),
                startip=vmpublic_startip.dotted(),
                endip=vmpublic_endip.dotted(),
                **additional
        )
    return vlaniprange


def create_zone(cs, name, dnsserver, internaldns, advanced_networking, guestcidr, hyperv, update, localstorage):
    zone = None
    if update:
        zone = minicloudstack.obj_if_exists(cs, "zones", name=name)
    if not zone:
        if advanced_networking:
            additional = dict(
                    networktype="Advanced",
                    guestcidraddress=guestcidr.cidr()
            )
        else:
            additional = dict(
                    networktype="Basic",
            )

        zone = cs.obj(
                "create zone",
                name=name,
                localstorageenabled=localstorage,
                dns1=dnsserver.dotted(),
                internaldns1=internaldns.dotted(),
                securitygroupenabled=False,
                **additional
        )
        if hyperv == "baremetal":
            cs.call("update zone", id=zone.id, dhcpprovider="ExternalDhcpServer")
        print("Zone created ({})".format(zone.id))

    return zone


def add_vmwaredc(cs, zone, datacenter, vcenter, username, password, update):
    vmwaredc = None
    if update:
        vmwaredc = minicloudstack.obj_if_exists(cs, "vmware dcs", zoneid=zone.id)
    if not vmwaredc:
        vmwaredc = cs.obj(
                "add vmware dc",
                zoneid=zone.id,
                name=datacenter,
                vcenter=vcenter,
                username=username,
                password=password
        )
        print("VMware DC added {} ({})".format(vmwaredc.name, vmwaredc.id))

    return vmwaredc


def get_secondary_storage_url_details(url):
    o = urlparse(url)
    query_string = o.query
    # Flatten out the key values to get single values from parse_qs:
    qs_dict = dict((k, v if len(v) > 1 else v[0])
        for k, v in parse_qs(query_string).items())
    return qs_dict


def get_primary_storage_url_details(url):
    o = urlparse(url)
    query_string = o.query
    # Flatten out the key values to get single values from parse_qs:
    qs_list = []
    for k, v in parse_qs(query_string).items():
        if len(v) == 1:
            v = v[0]
        qs_list.append({k: v})
    return qs_list


def create_storagepool(cs, zone, pod, cluster, hypervisor, storagepool_name, primarystorage, update):
    storagepool = None
    if update:
        storagepool = minicloudstack.obj_if_exists(cs, "storage pools", zoneid=zone.id, podid=pod.id, clusterid=cluster.id)
    if not storagepool:
        primarystorage_details = get_primary_storage_url_details(primarystorage)
        # strip off the query parameters if any
        primarystorage_url = primarystorage.split("?")[0]
        storagepool = cs.obj(
                "create storage pool",
                scope="cluster",
                zoneid=zone.id,
                clusterid=cluster.id,
                podid=pod.id,
                name=storagepool_name,
                url=primarystorage_url,
                details=primarystorage_details
        )
        print("Primary storage (storage pool) created ({})".format(storagepool.id))

    return storagepool


def create_imagestore(cs, zone, imagestore_name, secondarystorage, update):
    imagestore = None
    if update:
        imagestore = minicloudstack.obj_if_exists(cs, "image stores", zoneid=zone.id)
    if not imagestore:
        imagestore_protocol = urlparse(secondarystorage).scheme
        imagestore_protocol_uppercase = imagestore_protocol.upper()
        imagestore_details = get_secondary_storage_url_details(secondarystorage)

        # strip off the query parameters if any
        secondarystorage_url = secondarystorage.split("?")[0]

        params = {
            'zoneid': zone.id,
            'name': imagestore_name,
            'provider': imagestore_protocol_uppercase,
            'url': secondarystorage_url
        }

        if imagestore_details:
            params['details'] = imagestore_details

        imagestore = cs.obj("add image store", **params)
        print("Secondary storage (image store) created ({})".format(imagestore.id))

    return imagestore


def enable_securitygroups(cs, zone):
    try:
        cs.call("change zone security group status", zoneid=zone.id, enabled=True)
    except minicloudstack.MiniCloudStackException:
        print("Warning: Failed to enable security groups for zone - you need to do it manually in the DB")


def prevent_broadcast_ip(cidr, ip):
    result = ip
    if ip.dotted() == cidr.lastip().dotted():
        result = ip.new_adding(-1)
        if minicloudstack.get_verbosity() > 1:
            print("Preventing collision with broadcast IP {} -> {}".format(ip.dotted(), result.dotted()))
    return result


def create_all(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)

    mgmtnet = minicloudstack.IpCidr(arguments.mgmtnet)
    mgmtgateway = mgmtnet.ip()
    mgmtalloc = minicloudstack.IpCidr(arguments.mgmtalloc)
    mgmtdns = minicloudstack.IpAddress(arguments.mgmtdns)
    localstorage = arguments.localstorage

    if arguments.pubnet:
        pubnet = minicloudstack.IpCidr(arguments.pubnet)
        pubgateway = pubnet.ip()
    else:
        pubnet = mgmtnet
        pubgateway = mgmtgateway

    if arguments.puballoc:
        puballoc = minicloudstack.IpCidr(arguments.puballoc)

        mgmt_startip = mgmtalloc.firstip()
        mgmt_endip = prevent_broadcast_ip(mgmtnet, mgmtalloc.lastip())

        vmpublic_startip = puballoc.firstip()
        vmpublic_endip = puballoc.lastip()
    else:
        middle = mgmtalloc.firstip().new_adding((mgmtalloc.lastip().integer() - mgmtalloc.firstip().integer()) / 2)

        mgmt_startip = mgmtalloc.firstip()
        mgmt_endip = middle

        vmpublic_startip = middle.new_adding(1)
        vmpublic_endip = mgmtalloc.lastip()

    if arguments.pubdns:
        pubdns = minicloudstack.IpAddress(arguments.pubdns)
    else:
        pubdns = mgmtdns

    vmpublic_endip = prevent_broadcast_ip(pubnet, vmpublic_endip)

    if minicloudstack.get_verbosity():
        print("Mgmt network {}-{} [{} gw: {}] VLAN: '{}'".format(
                mgmt_startip.dotted(), mgmt_endip.dotted(),
                mgmtnet.cidr(), mgmtgateway.dotted(), arguments.mgmtvlan))
        print("VM public network {}-{} [{} gw: {}] VLAN: '{}'".format(
                vmpublic_startip.dotted(), vmpublic_endip.dotted(),
                pubnet.cidr(), pubgateway.dotted(), arguments.pubvlan))

    guestcidr = minicloudstack.IpCidr(arguments.guestcidr)

    adv_netw = not arguments.basic
    hypervisor = arguments.hypervisor

    zone = create_zone(cs, arguments.name, mgmtdns, pubdns, adv_netw, guestcidr, hypervisor, arguments.update, localstorage)

    pn_pu, pn_pr = create_physicalnetworks(cs, zone, hypervisor, adv_netw, arguments.mgmtvlan, arguments.pubvlan, arguments.guestvlan, arguments.update)

    podname = arguments.name + "-pod1"   # Assume no-one cares about pod name.
    pod = addhost.create_pod(cs, zone, podname, mgmtgateway, mgmtnet, mgmt_startip, mgmt_endip, arguments.update)

    if not adv_netw:
        # Basic networking zones need one network that is created here (advanced automatically creates network pr account).
        network_name = arguments.name + "-default"
        create_network(cs, zone, pn_pu, network_name, hypervisor, arguments.update)

    if hypervisor == "baremetal":
        create_vlaniprange(cs, zone, pod, pubgateway, pubnet, "untagged", vmpublic_startip, vmpublic_endip, arguments.update)
    else:
        create_vlaniprange(cs, zone, pod, pubgateway, pubnet, arguments.pubvlan, vmpublic_startip, vmpublic_endip, arguments.update)

    url = None
    if hypervisor == "vmware":
        url = "http://{}/{}/{}".format(arguments.host, arguments.datacenter, arguments.cluster)
        add_vmwaredc(cs, zone, arguments.datacenter, arguments.host, arguments.username, arguments.password, arguments.update)

    clustername = podname + "-" + hypervisor.lower() + "-cluster1"  # Assume no-one cares about cluster name.

    cluster = addhost.add_cluster(cs, zone, pod, clustername, hypervisor, arguments.username, arguments.password, url, arguments.update)

    if hypervisor == "kvm" or hypervisor == "hyperv":
        addhost.add_host(cs, zone, pod, cluster, hypervisor, arguments.host, arguments.username, arguments.password, arguments.update)
    elif hypervisor == 'baremetal':
        addhost.add_baremetal_host(cs, zone, pod, cluster, hypervisor, arguments.host, arguments.username, arguments.password, arguments.baremetalhostmac, arguments.baremetalcpuspeed, arguments.baremetalcpunumber, arguments.baremetalmemory, None, None, arguments.update)
    if hypervisor != "baremetal":
        if not localstorage:
            storagepool_name = clustername + "primary"   # Assume no-one cares...
            create_storagepool(cs, zone, pod, cluster, hypervisor, storagepool_name, arguments.primarystorage, arguments.update)

        imagestore_name = arguments.name + "secondary"   # Assume no-one cares...
        create_imagestore(cs, zone, imagestore_name, arguments.secondarystorage, arguments.update)

    if adv_netw:
        # Turn on security groups for zone:
        cs_major, cs_minor = cs.version()
        if cs_major == 4 and cs_minor == 2:
            enable_securitygroups(cs, zone)

    if localstorage:
        cs.obj("update configuration", name="system.vm.use.local.storage", value="true")

    if hypervisor == "baremetal":
        # We assume that the zone is basic baremetal, make and set up all PXE related stuff
        baremetal.post_baremetal_basic_zone_update(cs, pn_pu, pod, arguments)

    # Enable zone.
    cs.call("update zone", id=zone.id, allocationstate="Enabled")


def main():
    parser = argparse.ArgumentParser("Create a new zone")

    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    parser.add_argument("-up", "--update", action="store_true", default=False, help="Try to add missing components")

    mgmtnet = parser.add_argument_group("Management Network (required)", "Management servers (pod network)")
    mgmtnet.add_argument("-mn", "--mgmtnet", required=True, help="Gateway IP + CIDR")
    mgmtnet.add_argument("-ma", "--mgmtalloc", required=True, help="CIDR to allocte from")
    mgmtnet.add_argument("-md", "--mgmtdns", default="8.8.8.8", help="IP of DNS server")
    mgmtnet.add_argument("-mv", "--mgmtvlan", default="", help="Optional VLAN")

    pubnet = parser.add_argument_group("Public Network (optional)", "Public VM's (shares management if not specified)")
    pubnet.add_argument("-pn", "--pubnet", help="Gateway IP + CIDR")
    pubnet.add_argument("-pa", "--puballoc", help="CIDR to allocate from")
    pubnet.add_argument("-pd", "--pubdns", default="8.8.4.4", help="IP of DNS server")
    pubnet.add_argument("-pv", "--pubvlan", default="", help="Optional VLAN")

    addnet = parser.add_argument_group("Additional Network Configuration")
    addnet.add_argument("-ba", "--basic", action="store_true", default=False, help="Create basic networking zone")
    addnet.add_argument("-gc", "--guestcidr", default="10.1.1.0/24", help="CIDR for guest (advanced) network")
    addnet.add_argument("-gv", "--guestvlan", default="3900-4000", help="VLAN(s) for guest networks (advanced networking)")

    storage = parser.add_argument_group("Storage")
    storage.add_argument("-s1", "--primarystorage", required=False, help="nfs://server/path for primary storage")
    storage.add_argument("-s2", "--secondarystorage", required=False, help="nfs://server/path for secondary storage")
    storage.add_argument("-lo", "--localstorage", action="store_true", default=False, help="Enable local storage on the zone")

    baremetal = parser.add_argument_group("Baremetal")
    baremetal.add_argument("-bip", "--baremetalip", help="Bootserver IP for baremetal (docker container)")
    baremetal.add_argument("-bpw", "--baremetalpassword", help="Bootserver for baremetal password")
    baremetal.add_argument("-bhm", "--baremetalhostmac", help="First baremetal instance mac address")
    baremetal.add_argument("-bcs", "--baremetalcpuspeed", default="2400", help="First baremetal instance cpu speed (MHz)")
    baremetal.add_argument("-bcn", "--baremetalcpunumber", default="1", help="First baremetal instance cpu number")
    baremetal.add_argument("-bmb", "--baremetalmemory", default="2048", help="First baremetal instance memory (MB)")

    parser.add_argument("-hy", "--hypervisor", required=True, default="kvm",
                        choices=["kvm", "vmware", "hyperv", "baremetal"], help="Type of hypervisor cluster to add")

    parser.add_argument("-dc", "--datacenter", default="", help="vmware datacenter")
    parser.add_argument("-cl", "--cluster", default="", help="vmware cluster")

    parser.add_argument("-ho", "--host", required=False, help="Hypervisor/vCenter host to add to zone")
    parser.add_argument("-un", "--username", required=False, help="Hypervisor/vCenter login user")
    parser.add_argument("-pw", "--password", required=False, help="Hypervisor/vCenter login password")

    parser.add_argument("name", help="name of zone to create")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()

    if arguments.hypervisor == "vmware":
        if len(arguments.datacenter) == 0 or len(arguments.cluster) == 0:
            raise parser.error("You need to specify --datacenter and --cluster for vmware zones")

    if arguments.hypervisor == "baremetal":
        if not arguments.baremetalip:
            raise parser.error("You must specify IP of the baremetal bootserver (-bip or --baremetalip) when using a baremetal zone")

    if arguments.host is not None:
        if arguments.username is None or arguments.password is None:
            raise parser.error("You need to specify username AND pw when adding a host")
        if arguments.hypervisor != "baremetal":
            if arguments.primarystorage is None or arguments.secondarystorage is None:
                raise parser.error("You must specify primary and secondary storage when using option host")

    if arguments.hypervisor != "baremetal":
        if arguments.primarystorage is None or arguments.secondarystorage is None:
            raise parser.error("You must specify primary and secondary storage if you are creating something else than a baremetal zone")

    minicloudstack.set_verbosity(arguments.verbose)

    try:
        create_all(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if minicloudstack.get_verbosity() > 1:
            raise e
        else:
            print(" - - - ")
            print("Error creating zone:")
            print(e.message)


if __name__ == "__main__":
    main()
