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


def add_baremetal_service_offering(cs, host):
    service_offering = None
    cpunumber = host.cpunumber
    cpuspeed = host.cpuspeed
    hosttags = host.hosttags
    memory_b = int(host.memorytotal)
    memory_mb = memory_b/(1024*1024)
    memory_gb = round(float(memory_mb)/1024, 1)
    if memory_gb == int(memory_gb):
        memory_gb = int(memory_gb)
    if memory_mb < 1024:
        memory = "{0}m".format(memory_mb)
    else:
        memory = "{0}g".format(memory_gb)
    so_name = "bm.{0}.{1}.{2}".format(cpunumber, cpuspeed, memory)
    service_offering = minicloudstack.obj_if_exists(cs, "service offerings", name=so_name)
    so_displaytext = "Baremetal {0} CPU {1} MHz {2} RAM".format(cpunumber, cpuspeed, memory)
    if not service_offering:
        service_offering = cs.obj(
                "create service offering",
                name=so_name,
                displaytext=so_displaytext,
                cpunumber=cpunumber,
                cpuspeed=cpuspeed,
                memory=memory_mb,
                hosttags=hosttags
        )


def post_baremetal_basic_zone_update(cs, pu, pod, arguments, bootserver_user="root", bootserver_password="password"):
    baremetalip = arguments.baremetalip
    url = "http://" + baremetalip + "/"
    tftpdir = "/var/lib/tftpboot/"
    username = bootserver_user
    password = bootserver_password
    cs.call("add baremetal dhcp",
            physicalnetworkid=pu.id,
            dhcpservertype="DHCPD",
            username=username,
            password=password,
            url=url)

    cs.call("add baremetal pxe kick start server",
            physicalnetworkid=pu.id,
            username=username,
            password=password,
            tftpdir=tftpdir,
            url=url,
            pxeservertype="KICK_START",
            podid=pod.id)

    cs.call("add baremetal basic pxe server",
            physicalnetworkid=pu.id,
            username=username,
            password=password,
            tftpdir=tftpdir,
            url=url,
            pxeservertype="BASIC_PXE",
            podid=pod.id)


def add_baremetal_advanced_switch(cs, ipaddress, username, password, switch_type):
    switch = cs.obj("add baremetal switch",
            ipaddress=ipaddress,
            username=username,
            password=password,
            type=switch_type)
    print("Baremetal switch added ({})".format(switch.id))
    return switch


def main():
    parser = argparse.ArgumentParser("minicloudstack baremetal")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")
    minicloudstack.add_arguments(parser)

    switch = parser.add_argument_group("Add Baremetal Advanced Switch", "Switch properties")
    switch.add_argument("-as", "--addswitch", action="store_true",  help="Add Baremetal Advanced switch")
    switch.add_argument("-sip", "--switchip", help="Switch ip")
    switch.add_argument("-su", "--switchusername", help="Switch username")
    switch.add_argument("-sp", "--switchpassword", help="Switch password")
    switch.add_argument("-st", "--switchtype", default="DellS4810", help="Switch type")

    arguments = parser.parse_args()

    minicloudstack.set_verbosity(arguments.verbose)

    try:
        if arguments.addswitch:
            cs = minicloudstack.MiniCloudStack(arguments)
            add_baremetal_advanced_switch(cs, arguments.switchip, arguments.switchusername, arguments.switchpassword, arguments.switchtype)
    except minicloudstack.MiniCloudStackException as e:
        if minicloudstack.get_verbosity() > 1:
            raise e
        else:
            print(" - - - ")
            print("Error:")
            print(e.message)


if __name__ == "__main__":
    main()
