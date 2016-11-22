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

from . import mcs as minicloudstack
from . import baremetal


def add_host(cs, zone, pod, cluster, hypervisor, host_url, username, password, update):
    host = None
    if update:
        host = minicloudstack.obj_if_exists(cs, "hosts", clusterid=cluster.id, hypervisor=hypervisor)
    if not host:
        if not host_url.startswith("http://") or not host_url.startswith("https://"):
            host_url = "http://" + host_url
        host = cs.obj(
                "add host",
                zoneid=zone.id,
                podid=pod.id,
                clusterid=cluster.id,
                url=host_url,
                username=username,
                password=password,
                hypervisor=hypervisor
        )
        print("Host created ({})".format(host.id))

    return host


def add_baremetal_host(cs, zone, pod, cluster, hypervisor, host_url, username, password, hostmac, cpuspeed, cpunumber, memory, switchid, switchport, update):
    host = None
    if host_url:
        if update:
            host = minicloudstack.obj_if_exists(cs, "hosts", clusterid=cluster.id, hypervisor=hypervisor)
        if not host:
            if not host_url.startswith("http://") or not host_url.startswith("https://"):
                host_url = "http://" + host_url
            hosttags = "BareMetal"
            additional = dict()
            if switchport: 
                if not switchid:
                    # Pick first switch if not specified
                    switches = cs.map("baremetal switches")
                    if len(switches) != 1:
                        print("Error: This script only works if you have exactly one baremetal switch 'in the zone'")
                        return False
                    switchid, switch = switches.popitem()
                    switchid = switch.id
                additional = dict(
                        switchid=switchid,
                        switchport=switchport
                )
            host = cs.obj(
                    "add baremetal host",
                    zoneid=zone.id,
                    podid=pod.id,
                    clusterid=cluster.id,
                    url=host_url,
                    username=username,
                    password=password,
                    hostmac=hostmac,
                    cpuspeed=cpuspeed,
                    cpunumber=cpunumber,
                    memory=memory,
                    hypervisor=hypervisor,
                    hosttags=hosttags,
                    **additional
            )
            print("Host created ({})".format(host.id))
            baremetal.add_baremetal_service_offering(cs, host)
    return host


def create_pod(cs, zone, podname, gateway, podcidr, mgmt_startip, mgmt_endip, update):
    pod = None
    if update:
        pod = minicloudstack.obj_if_exists(cs, "pods", zoneid=zone.id)
    if not pod:
        pod = cs.obj(
                "create pod",
                zoneid=zone.id,
                name=podname,
                startip=mgmt_startip.dotted(),
                endip=mgmt_endip.dotted(),
                gateway=gateway.dotted(),
                netmask=podcidr.netmask().dotted(),
        )

        print("Pod created {} ({})".format(pod.name, pod.id))
    return pod


def add_cluster(cs, zone, pod, clustername, hypervisor, username, password, url, update):
    cluster = None
    if update:
        cluster = minicloudstack.obj_if_exists(cs, "clusters", zoneid=zone.id, podid=pod.id)
    if not cluster:
        if hypervisor == "vmware":
            additional = dict(
                    clustertype="ExternalManaged",
                    username=username,
                    password=password,
                    url=url,
            )
        else:
            additional = dict(
                    clustertype="CloudManaged",
            )

        cluster = cs.obj(
                "add cluster",
                zoneid=zone.id,
                podid=pod.id,
                clustername=clustername,
                hypervisor=hypervisor,
                **additional
        )
        print("Cluster created {} ({})".format(cluster.name, cluster.id))

    return cluster


def add_host_default(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)
    hypervisor = arguments.hypervisor

    zone = cs.obj("list zones", name=arguments.zone)
    if minicloudstack.get_verbosity():
        print("Found zone [{}]".format(zone.id))

    pods = cs.map("pods", zoneid=zone.id)
    if len(pods) != 1:
        print("Error: This script only works if you have exactly one pod 'in the zone'")
        return False

    podid, pod = pods.popitem()
    if minicloudstack.get_verbosity():
        print("Found pod {} [{}] in zone".format(pod.name, pod.id))

    clusters = cs.map("clusters", zoneid=zone.id, podid=pod.id, hypervisor=arguments.hypervisor)
    if len(clusters) == 0:
        # For baremetal advanced, we need to make sure there exists an additional cluster
        clustername = pod.name + "-" + hypervisor.lower() + "-cluster1"
        cluster = add_cluster(cs, zone, pod, clustername, hypervisor, None, None, None, False)
    else:
        clusterid, cluster = clusters.popitem()

    if minicloudstack.get_verbosity():
        print("Found cluster {} [{}] in pod".format(cluster.name, cluster.id))

    host_url = arguments.host
    hypervisor = arguments.hypervisor
    username = arguments.username
    password = arguments.password
    update = False

    if hypervisor == 'baremetal':
        baremetalhostmac = arguments.baremetalhostmac
        baremetalcpuspeed = arguments.baremetalcpuspeed
        baremetalcpunumber = arguments.baremetalcpunumber
        baremetalmemory = arguments.baremetalmemory
        baremetalswitchid = arguments.baremetalswitchid
        baremetalswitchport = arguments.baremetalswitchport
        host = add_baremetal_host(cs, zone, pod, cluster, hypervisor, host_url, username, password, baremetalhostmac, baremetalcpuspeed, baremetalcpunumber, baremetalmemory, baremetalswitchid, baremetalswitchport, update)
    else:
        host = add_host(cs, zone, pod, cluster, hypervisor, host_url, username, password, update)

    print("Host added [{}]".format(host.id))


def main():
    parser = argparse.ArgumentParser("Add a host to an existing zone")

    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    parser.add_argument("-z", "--zone", required=True, help="Name of zone to add host to")
    parser.add_argument("-ho", "--host", required=True, help="Hypervisor host to add to zone")
    parser.add_argument("-un", "--username", required=True, help="Hypervisor login user")
    parser.add_argument("-pw", "--password", required=True, help="Hypervisor login password")
    parser.add_argument("-bhm", "--baremetalhostmac", help="First baremetal instance mac address")
    parser.add_argument("-bcs", "--baremetalcpuspeed", default="2400", help="First baremetal instance cpu speed (MHz)")
    parser.add_argument("-bcn", "--baremetalcpunumber", default="1", help="First baremetal instance cpu number")
    parser.add_argument("-bmb", "--baremetalmemory", default="2048", help="First baremetal instance memory (MB)")
    parser.add_argument("-bsi", "--baremetalswitchid", help="Baremetal Switch id")
    parser.add_argument("-bsp", "--baremetalswitchport", help="Baremetal Switch Port")
    parser.add_argument("-hy", "--hypervisor", required=True, default="kvm",
                        choices=["kvm", "vmware", "hyperv", "baremetal"], help="Type of hypervisor cluster to add")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()

    minicloudstack.set_verbosity(arguments.verbose)

    try:
        add_host_default(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if minicloudstack.get_verbosity() > 1:
            raise e
        else:
            print(" - - - ")
            print("Error adding host:")
            print(e.message)


if __name__ == "__main__":
    main()
