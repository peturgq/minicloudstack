#!/usr/bin/env python
#
# Copyright 2015-2016 Greenqloud ehf
#
# sverrir@greenqloud.com
#
# Register a template
#

import minicloudstack

import argparse

verbose = 0
DEFAULT_OSTYPE = "Other Linux (64-bit)"


def obj_if_exists(cs, type, **kwargs):
    results = cs.map(type, **kwargs)
    if len(results.keys()) > 1:
        print "Warning: more than one object found in '{}".format(type)
    elif len(results.keys()) == 1:
        key, value = results.popitem()
        if verbose:
            print "Found existing object '{}' with id '{}'".format(type, key)
        return value
    else:
        return None


def register_template(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)

    zone = obj_if_exists(cs, "zones", name=arguments.zone)

    ostype = DEFAULT_OSTYPE
    ostype = obj_if_exists(cs, "os types", description=ostype)
    if verbose:
        print("Using ostype $%s [%s]", ostype.description, ostype.id)

    cs.call("register template",
            name=arguments.name,
            displaytext=arguments.name,
            hypervisor=arguments.hypervisor,
            format=arguments.format,
            url=arguments.location,
            isfeatured=True,
            ispublic=True,
            ostypeid=ostype.id,
            zoneid=zone.id)


def main():
    global verbose

    parser = argparse.ArgumentParser("Register a template")

    parser.add_argument("-v",  "--verbose", action="count", help="Increase output verbosity")

    parser.add_argument("-hy", "--hypervisor", default="kvm",
                        choices=["kvm", "vmware", "hyperv", "baremetal"], help="Type of hypervisor cluster to add")

    parser.add_argument("-fo", "--format", default="qcow2",
                        choices=["qcow2", "raw", "vhd", "ova", "iso", "vhdx", "baremetal", "vmdk", "vdi", "tar", "dir"],
                        help="Format of template")

    parser.add_argument("-z", "--zone", required=True, help="Name of zone to register too")

    parser.add_argument("name", help="name of template")

    parser.add_argument("location", help="location of template")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()

    verbose = arguments.verbose
    minicloudstack.set_verbosity(arguments.verbose)

    try:
        register_template(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if verbose > 1:
            raise e
        else:
            print(" - - - ")
            print("Error registering zone:")
            print(e.message)
            exit(1)


if __name__ == "__main__":
    main()
