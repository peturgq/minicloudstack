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

DEFAULT_OSTYPE = "Other Linux (64-bit)"


def register_template(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)

    if arguments.zone == "-1":
        # Special case meaning "all" zones.
        zoneid = arguments.zone
    else:
        zone = minicloudstack.obj_if_exists(cs, "zones", name=arguments.zone)
        zoneid = zone.id

    ostype = minicloudstack.obj_if_exists(cs, "os types", description=arguments.ostype)
    if not ostype:
        print("Failed to find OS Type: \"{}\"".format(arguments.ostype))
        print("You can try any of these:")
        descriptions = [ ostype.description for ostype in cs.map("os types").values()]
        for desc in sorted(descriptions):
            print("\"{}\"".format(desc))
        exit(1)

    if minicloudstack.get_verbosity():
        print("Using OS Type {} [{}]".format(ostype.description, ostype.id))

    templates = cs.call(
        "register template",
        name=arguments.name,
        displaytext=arguments.name,
        hypervisor=arguments.hypervisor,
        format=arguments.format,
        url=arguments.location,
        isfeatured=True,
        ispublic=True,
        passwordenabled=arguments.password,
        sshkeyenabled=arguments.ssh,
        ostypeid=ostype.id,
        zoneid=zoneid)

    # Assuming the template id to be the same across zones.  Displaying first one found.
    print(templates["template"][0]["id"])


def main():
    parser = argparse.ArgumentParser("Register a template")

    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    parser.add_argument("-hy", "--hypervisor", default="kvm",
                        choices=["kvm", "vmware", "hyperv", "baremetal"], help="Type of hypervisor cluster to add")

    parser.add_argument("-fo", "--format", default="qcow2",
                        choices=["qcow2", "raw", "vhd", "ova", "iso", "vhdx", "baremetal", "vmdk", "vdi", "tar", "dir"],
                        help="Format of template")

    parser.add_argument("--ostype", default=DEFAULT_OSTYPE, help="OS Type (see CS documentation)")
    parser.add_argument("-z", "--zone", default="-1", help="Name of zone to register in (skip for all zones)")

    parser.add_argument("--password", dest="password", action="store_true", help="Password support")
    parser.add_argument("--no-password", dest="password", action="store_false", help="No password support")
    parser.set_defaults(password=False)

    parser.add_argument("--ssh", dest="ssh", action="store_true", help="SSH key support")
    parser.add_argument("--no-ssh", dest="ssh", action="store_false", help="No SSH key support")
    parser.set_defaults(ssh=False)

    parser.add_argument("name", help="name of template")

    parser.add_argument("location", help="location of template")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()

    minicloudstack.set_verbosity(arguments.verbose)

    try:
        register_template(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if minicloudstack.get_verbosity() > 1:
            raise e
        else:
            print(" - - - ")
            print("Error registering zone:")
            print(e)
            exit(1)


if __name__ == "__main__":
    main()
