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
import json
import logging
import os
import platform
import stat
import subprocess

from . import mcs as minicloudstack

LOG_FILE = None


def out_error(output):
    if LOG_FILE:
        logging.error(output)
    else:
        print(output)


def out_warn(output):
    if LOG_FILE:
        logging.warn(output)
    else:
        print(output)


def out_info(output):
    if LOG_FILE:
        logging.info(output)
    else:
        print(output)


def out_debug(output):
    if LOG_FILE:
        logging.debug(output)
    elif minicloudstack.get_verbosity() > 1:
        print(output)


def result(exitcode, status, message, device=None, volume=None):
    r = {
        "status": status,
        "message": message
    }
    if device:
        r["device"] = device
    if volume:
        r["volume"] = volume
    if LOG_FILE:
        print(json.dumps(r))
    return exitcode


def success(message=None, device=None, volume=None):
    message = message or "Action completed successfully"
    out_info("Success: {} ({})".format(message, device or volume or "<empty>"))
    return result(0, "Success", message, device, volume)


def error(message):
    out_error(message)
    return result(1, "Failure", message)


def shell(cmd):
    out_debug("shell: '{}'".format(cmd))
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    stdout, stderr = p.communicate()
    if len(stderr):
        out_warn("shell: Execute warning '{}': {}".format(cmd, stderr.decode()))
    if p.returncode != 0:
        out_error("shell: Failed to execute '{}' [{}]".format(cmd, p.returncode))
        return ""
    output = stdout.decode()
    if len(output) == 0:
        output = "OK"
    out_debug("shell: '{}' output: {}".format(cmd, output))
    return output


def device_id_to_name(device_id):
    """
    Tries to come up with educated guess of the device name from CloudStack device-id.
    :param device_id: CloudStack device-id
    :return: physical device name
    """
    primary_disk = None
    for line in shell("lsblk -n").split("\n"):
        items = line.split()
        if "disk" in items:
            disk = items[0]
            if disk.endswith("a"):
                primary_disk = disk
                break

    if not primary_disk:
        return None

    if device_id > 3:   # Device id 3 reserved for CDROM
        device_id -= 1

    device_name = primary_disk[:-1] + chr(ord("a") + device_id)

    return "/dev/{}".format(device_name)


def device_name_to_id(device_name):
    """
    Tries to come up with CloudStack device-id based on physical device name.
    Assumes you have validated this as a proper device name (see 'is_block_device').
    :param device_name: path to device
    :return: CloudStack device-id
    """
    short = device_name.split("/")[-1]
    last_char = short[-1]
    num = ord(last_char) - ord("a")
    if num > 2:     # Device id 3 reserved for CDROM
        num += 1
    return num


def is_block_device(device_name):
    """
    :param device_name: e.g. "/dev/vdb"
    :return: True if this is a block device (and therefore likely an attached disk)
    """
    if not os.path.exists(device_name):
        return False

    mode = os.stat(device_name).st_mode
    return stat.S_ISBLK(mode)


def format_disk_if_required(device_name, file_system):
    """
    Checks if device has been formatted and if not formats with 'file_system'.
    :param device_name: the physical device (e.g. /dev/vdb)
    :param file_system: file system to use (e.g. ext4)
    :return: True if successful or no formatting required
    """
    for line in shell("lsblk -n --fs {}".format(device_name)).split("\n"):
        items = line.split()
        if file_system in items:
            return True

    out_info("Formatting disk on {} wih file system {}".format(device_name, file_system))

    output = shell("mkfs -t {file_system} {device_name}".format(
                   file_system=file_system,
                   device_name=device_name))

    return len(output) > 0


def size_in_gigabytes(s):
    """
    Convert disk size from human readable (1000m, 1t) to gigabytes ( 2000m -> 2 )
    :param s: human readable disk size
    :return: integer number of gigabytes (at least 1)
    """
    s = s.lower()
    factor = 1
    if s.endswith("m"):
        factor = 1000 ** 2
        s = s[:-1]
    elif s.endswith("g"):
        factor = 1000 ** 3
        s = s[:-1]
    elif s.endswith("t"):
        factor = 1000 ** 4
        s = s[:-1]
    else:   # By default assume gigabytes
        factor = 1000 ** 3
    size = int(s) * factor
    gb = size / (1000 ** 3)
    # Assume rounding errors.  size 0 or negative is not really useful.
    return max(int(gb), 1)


def find_cloudstack_volume(mcs, vm_id, device_id=None, volume_id=None):
    volume = None
    for v in mcs.list("volumes"):
        attached_vm = getattr(v, "virtualmachineid", vm_id)
        if attached_vm == vm_id or getattr(v, "vmstate", "") == "Stopped":
            # Volume is already attached to this VM, no VM or Stopped VM.
            if volume_id and v.id == volume_id:
                volume = v
                break
            if device_id and getattr(v, "deviceid", -1) == device_id:
                volume = v
                break

    return volume


def is_json_options(s):
    try:
        options = json.loads(s)
        return isinstance(options, dict)
    except ValueError:
        return False


def parse_options(s):
    fstype = "ext4"
    volumeid = None
    if not is_json_options(s):
        return s, fstype

    options = json.loads(s)
    for k in options.keys():
        if "fstype" in k.lower():
            fstype = options[k]
        elif "volumeid" in k.lower():
            volumeid = options[k]
    return volumeid, fstype


def init(mcs, args):
    return success("Initialized")


def create(mcs, args):
    vm_id = args.vmid
    if is_json_options(args.options):
        options = json.loads(args.options)
        size = options.get("size", "1g")
    else:
        size = args.options
    gigabytes = size_in_gigabytes(size)
    out_info("Creating volume of size {}g in zone of VM {}...".format(gigabytes, vm_id))
    try:
        # Get disk offering (using the first customizable found).
        disk_offering = None
        for do in mcs.list("disk offerings"):
            if do.iscustomized and do.displayoffering:
                disk_offering = do
                break
        if not disk_offering:
            return error("Could not find customizable disk offering")

        # Find zone.
        vms = mcs.list("virtual machines", id=vm_id)
        if len(vms) != 1:
            return error("Can't figure out zone of virtual machine {}".format(vm_id))
        vm = vms[0]
        out_info("Creating volume using disk offering {} in zone {}...".format(
            disk_offering.id, vm.zonename))
        new_vol = mcs.obj("create volume", zoneid=vm.zoneid, diskofferingid=disk_offering.id, size=gigabytes)
        return success("Created volume", volume=new_vol.id)
    except minicloudstack.MiniCloudStackException as e:
        return error("Volume create failed: {}".format(e))


def delete(mcs, args):
    volume_id, _ = parse_options(args.options)
    out_info("Deleting volume {}...".format(volume_id))
    try:
        mcs.call("delete volume", id=volume_id)
        return success("Deleted volume", volume=volume_id)
    except minicloudstack.MiniCloudStackException as e:
        return error("Volume create failed: {}".format(e))


def attach(mcs, args):
    volume_id, _ = parse_options(args.options)
    if not volume_id:
        return error("missing volumeID")
    vm_id = args.vmid
    out_info("Attaching device for volume {} to VM {}...".format(volume_id, vm_id))
    try:
        volume = find_cloudstack_volume(mcs, vm_id, volume_id=volume_id)
        if not volume:
            return error("No matching volume found")

        if getattr(volume, "virtualmachineid", vm_id) != vm_id:
            # Already attached to another stopped VM.
            out_warn("Detaching from VM {} since that one is in Stopped state".format(volume.virtualmachineid))
            volume = mcs.obj("detach volume", id=volume.id)
        if not hasattr(volume, "deviceid"):
            volume = mcs.obj("attach volume", id=volume_id, virtualmachineid=vm_id)
        device_name = device_id_to_name(volume.deviceid)
        return success("Attached device successfully", device=device_name)
    except minicloudstack.MiniCloudStackException as e:
        return error("Device attach failed: {}".format(e))


def detach(mcs, args):
    device = args.device
    if not is_block_device(device):
        return error("Device {} is not a block device", device)
    device_id = device_name_to_id(device)
    vm_id = args.vmid
    out_info("Detaching device {} [{}] from VM {}...".format(device, device_id, vm_id))

    try:
        volume = find_cloudstack_volume(mcs, vm_id, device_id=device_id)
        if not volume:
            return error("Volume not found while detaching device {} [{}] from VM {}".format(
                device, device_id, vm_id))

        out_info("Detaching volume [{}]".format(volume.id))
        mcs.call("detach volume", id=volume.id)
        return success("Detached device successfully", volume=volume.id)
    except minicloudstack.MiniCloudStackException as e:
        return error("Volume detach failed: {}".format(e))


def mount(mcs, args):
    directory = args.target
    device = args.device
    volume_id, fs_type = parse_options(args.options)
    vm_id = args.vmid
    if not volume_id:
        return error("missing volumeID")

    volume = find_cloudstack_volume(mcs, vm_id, volume_id=volume_id)
    if not volume:
        return error("No matching volume found while mounting")

    out_info("Mounting {} to {}".format(directory, device))
    if not format_disk_if_required(device, fs_type):
        return error("Failed to format disk")

    if not os.path.exists(directory):
        out_debug("Creating directory {}".format(directory))
        os.makedirs(directory)

    if not shell("mount {device} {directory}".format(device=device, directory=directory)):
        return error("Failed to mount device")

    return success("Volume mounted successfully for {}".format(device))


def unmount(mcs, args):
    directory = args.volume

    if not shell("umount {directory}".format(directory=directory)):
        return error("Failed to unmount device")

    out_info("Removing mount directory {}".format(directory))
    os.rmdir(directory)

    return success("Volume unmounted successfully: {}".format(directory))


def main():
    parser = argparse.ArgumentParser(description="CloudStack Local Volume Management")
    minicloudstack.add_arguments(parser)

    parser.add_argument("--logfile", help="Log file name")
    parser.add_argument("-z", "--zone", help="Name of zone (if not zone of current vm)")
    parser.add_argument("-n", "--vmid", default=platform.node(),
                        help="Virtualmachine ID to use")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    commands = parser.add_subparsers(dest='command',
                                     help="<command> --help for command arguments")

    init_parser = commands.add_parser("init", help="Initialize")
    init_parser.set_defaults(func=init)

    attach_parser = commands.add_parser("create", help="Create volume")
    attach_parser.add_argument("options", help="size (in GB or options in json format)")
    attach_parser.set_defaults(func=create)

    attach_parser = commands.add_parser("delete", help="Delete volume")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=delete)

    attach_parser = commands.add_parser("attach", help="Attach volume")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=attach)

    attach_parser = commands.add_parser("detach", help="Detach volume")
    attach_parser.add_argument("device", help="Mount device")
    attach_parser.set_defaults(func=detach)

    attach_parser = commands.add_parser("mount", help="Mount volume")
    attach_parser.add_argument("target", help="Target mount directory")
    attach_parser.add_argument("device", help="Mount device")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=mount)

    attach_parser = commands.add_parser("unmount", help="Unmount volume")
    attach_parser.add_argument("volume", help="Volume to unmount")
    attach_parser.set_defaults(func=unmount)

    args = parser.parse_args()
    if not args.command:
        parser.error("You need to specify <command> (--help for more information)")

    minicloudstack.set_verbosity(args.verbose)

    if args.logfile:
        global LOG_FILE
        LOG_FILE = args.logfile
        level = logging.INFO
        if args.verbose > 1:
            level = logging.DEBUG
        logging.basicConfig(filename=args.logfile, level=level)

    try:
        mcs = minicloudstack.MiniCloudStack(args)
        return args.func(mcs, args)
    except Exception as e:
        error_message = "EXCEPTION: {}".format(e)
        logging.error(error_message)
        return error(error_message)


if __name__ == "__main__":
    exit(main())
