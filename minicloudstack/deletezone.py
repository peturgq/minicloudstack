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
import time

from . import mcs as minicloudstack


def handle_exception(ignore, exception):
    if ignore:
        print("WARNING - Ignoring problem:", exception.message)
    else:
        raise exception


def is_set(obj, attr):
    if hasattr(obj, attr):
        return getattr(obj, attr)
    return False


def delete_zone(cs, zone, force=False, ignore=False):
    print("Deleting {} [{}]".format(zone.name, zone.id))

    # Prevent anything to be created in the zone
    if zone.allocationstate == "Enabled":
        cs.call("update zone", id=zone.id, allocationstate="Disabled")

    # Set hosts to maintenance mode
    hosts = cs.map("hosts", zoneid=zone.id, type="Routing")
    wait_for_hosts = []
    for hid, host in hosts.items():
        if host.state == "Up" and host.resourcestate != "Maintenance":
            cs.call("prepare host for maintenance", id=hid)
            if host.clustertype == "CloudManaged":
                # CS requires host to be in maintenance before deletion (but vmware state never changes).
                wait_for_hosts.append(hid)

    # Wait for the host to be in maintenance mode
    while len(wait_for_hosts) > 0:
        hid = wait_for_hosts[0]
        host = cs.obj("list hosts", id=hid)
        if host.resourcestate == "Maintenance":
            wait_for_hosts.remove(hid)
            continue
        elif minicloudstack.get_verbosity():
            print("Host {} in {} mode".format(hid, host.resourcestate))
        time.sleep(5)

    # Destroy all VM's
    virtualmachines = cs.map("virtual machines", zoneid=zone.id, listall=True)
    for vmid, virtualmachine in virtualmachines.items():
        try:
            cs.call("destroy virtual machine", id=vmid, expunge=True)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Destroy all Routers
    routers = cs.map("routers", zoneid=zone.id, listall=True)
    for rid, router in routers.items():
        try:
            cs.call("destroy router", id=rid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete system VM's
    systemvms = cs.map("system vms", zoneid=zone.id)
    for svmid, svm in systemvms.items():
        try:
            cs.call("destroy system vm", id=svmid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete hosts
    for hid, host in hosts.items():
        try:
            cs.delete("host", id=hid, forced=force, forcedestroylocalstorage=force)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete ip-addresses
    ipaddresses = cs.map("public ip addresses", zoneid=zone.id, listall=True)
    for ipid, ipaddress in ipaddresses.items():
        try:
            if not ipaddress.issourcenat:
                cs.call("disassociate ip address", id=ipid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete networks
    networks = cs.map("networks", zoneid=zone.id)
    for nid, network in networks.items():
        try:
            cs.delete("network", id=nid, forced=force)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete physical networks
    physicalnetworks = cs.map("physical networks", zoneid=zone.id)
    for pnid, pn in physicalnetworks.items():
        try:
            cs.delete("physical network", id=pnid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete volumes
    volumes = cs.map("volumes", zoneid=zone.id, listall=True)
    for vid, volume in volumes.items():
        try:
            cs.delete("volume", id=vid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete templates
    templates = cs.map("templates", zoneid=zone.id, templatefilter="all")
    for tid, template in templates.items():
        try:
            if not (is_set(template, "crosszones") or is_set(template, "crossZones")):
                cs.delete("template", id=tid, zoneid=zone.id)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete storage pools
    storagepools = cs.map("storage pools", zoneid=zone.id)
    for spid, pool in storagepools.items():
        try:
            if pool.state != "Maintenance":
                cs.call("enable storage maintenance", id=spid)
            cs.delete("storage pool", id=spid, forced=force)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete clusters
    clusters = cs.map("clusters", zoneid=zone.id)
    for cid, cluster in clusters.items():
        try:
            cs.delete("cluster", id=cid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete vmwaredc's
    try:
        vmwaredcs = cs.map("vmware dcs", zoneid=zone.id)
        for vmwaredc in vmwaredcs.values():
            try:
                cs.call("remove vmware dc", id=vmwaredc.id, zoneid=zone.id)
            except minicloudstack.MiniCloudStackException as e:
                handle_exception(ignore, e)
    except Exception as e:
        handle_exception(ignore, e)
    # Delete pods
    pods = cs.map("pods", zoneid=zone.id)
    for pid, pod in pods.items():
        try:
            cs.delete("pod", id=pid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # Delete image stores
    imagestores = cs.map("image stores", zoneid=zone.id)
    for isid, store in imagestores.items():
        try:
            cs.delete("image store", id=isid)
        except minicloudstack.MiniCloudStackException as e:
            handle_exception(ignore, e)

    # TODO: Security groups?
    cs.delete("zone", id=zone.id)


def delete_zones(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)

    zones = cs.map("zones")

    delete_zone_ids = []
    if arguments.all:
        delete_zone_ids = zones.keys()
    else:
        for candidate in arguments.name:
            found_id = None
            for zid, zone in zones.items():
                if candidate == zid or candidate == zone.name:
                    found_id = zid
                    break
            if found_id:
                delete_zone_ids.append(found_id)
            else:
                print("Warning: zone '{}' not found".format(candidate))

    if len(delete_zone_ids) == 0:
        names = [z.name for z in zones.values()]
        names.sort()
        print("Please specify zone to delete ({})".format(", ".join(names)))
        return

    for zoneid in delete_zone_ids:
        delete_zone(cs, zones[zoneid], arguments.force, arguments.ignore)


def main():
    parser = argparse.ArgumentParser(usage="Destroys zone(s) - WITH EVERYTHING IN THEM!!!")

    minicloudstack.add_arguments(parser)

    parser.add_argument("-f", "--force", dest="force", action="store_true", default=False,
                        help="Force deletion of everything related to zone")

    parser.add_argument("-i", "--ignore", dest="ignore", action="store_true", default=False,
                        help="Ignore errors")

    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")
    parser.add_argument("--all", action="store_true", default=False,
                        help="Delete all zones")

    parser.add_argument("name", nargs="*", help="name of zone(s) to delete (can be uuid)")

    arguments = parser.parse_args()

    minicloudstack.set_verbosity(arguments.verbose)

    try:
        delete_zones(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if minicloudstack.get_verbosity() > 1:
            raise e
        else:
            print(" - - - ")
            print("Error deleting zone:")
            print(e.message)


if __name__ == "__main__":
    main()
