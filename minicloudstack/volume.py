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
import sys
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


def cmd_result(exitcode, status, message, device=None, volume=None, volume_name=None, attached=None):
    r = {
        "status": status,
        "message": message
    }
    if device:
        r["device"] = device
    if volume:
        r["volume"] = volume
    if volume_name:
        r["volumeName"] = volume_name
    if attached is not None:
        if attached:
            r["attached"] = "true"
        else:
            r["attached"] = "false"
    if LOG_FILE:
        if exitcode == 0:
            print(json.dumps(r))
        else:
            print(json.dumps(r), file=sys.stderr)
    return exitcode


def cmd_success(message=None, device=None, volume=None, volume_name=None, attached=None):
    message = message or "Action completed successfully"
    out_info("Success: {} ({})".format(message, device or volume or volume_name or attached or "<empty>"))
    return cmd_result(0, "Success", message, device, volume, volume_name, attached)


def cmd_error(message):
    out_error(message)
    return cmd_result(1, "Failure", message)


def shell(cmd):
    """
    Execute shell command
    :param cmd: command with arguments
    :return: if successful output of command (or OK) - empty response on failure
    """
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
    Warning: Must be run from within the VM being attached to to work.
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
    Returns 1 as minimum.
    :param s: human readable disk size
    :return: integer number of gigabytes (at least 1)
    """
    s = str(s).lower()
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


def create(mcs, size, vm_id=None, zone_id=None, attach=False):
    """
    Create volume.  You need to provide either 'vm_id' or 'zone_id' to create the volume
    in the correct place.
    :param mcs: MiniCloudStack instance with valid connection
    :param size: examples '10G', '1t'
    :param vm_id: id of virtual machine
    :param zone_id: id of zone
    :param attach: If True and 'vm_id' is provided. Attaches volume automatically
    :return: volume object
    """
    gigabytes = size_in_gigabytes(size)
    if not vm_id and not zone_id:
        raise minicloudstack.MiniCloudStackException("Missing vm_id or zone_id")
    if attach and not vm_id:
        raise minicloudstack.MiniCloudStackException("Cannot attach a volume without vm_id")
    # Get disk offering (using the first customizable found).
    disk_offering = None
    for do in mcs.list("disk offerings"):
        if do.iscustomized and do.displayoffering:
            disk_offering = do
            break
    if not disk_offering:
        raise minicloudstack.MiniCloudStackException("Could not find customizable disk offering")

    if not zone_id:
        # Find zone.
        vms = mcs.list("virtual machines", id=vm_id)
        if len(vms) != 1:
            raise minicloudstack.MiniCloudStackException("Can't figure out zone of virtual machine {}".format(vm_id))
        vm = vms[0]
        zone_id = vm.zoneid
    new_vol = mcs.obj("create volume", zoneid=zone_id, diskofferingid=disk_offering.id, size=gigabytes)
    if attach:
        new_vol = mcs.obj("attach volume", id=new_vol.id, virtualmachineid=vm_id)
    return new_vol


def mount(mcs, volume, directory, fs_type="ext4"):
    """
    Mount volume to local machine directory 'directory'. Volume is formatted if required with fs 'fs_type'.
    Warning: Assumes this volume has already been attached to current VM.  Use 'create_volume' with attach=True.
    :param mcs: MiniCloudStack instance with valid connection
    :param volume: volume object (e.g. from 'create_volume')
    :param directory: Folder to mount to (created if necessary)
    :param fs_type: filesystem to format the disk with if not formatted
    """
    device = device_id_to_name(volume.deviceid)
    if not format_disk_if_required(device, fs_type):
        raise minicloudstack.MiniCloudStackException(
            "Failed to format disk on {} with fs {}".format(device, fs_type))

    if not os.path.exists(directory):
        os.makedirs(directory)

    if not shell("mount {device} {directory}".format(device=device, directory=directory)):
        raise minicloudstack.MiniCloudStackException(
            "Failed to mount device {} to directory {}".format(device, directory))


def unmount(mcs, directory, delete_after=True):
    """
    Unmount directory.  This is the reverse action of 'mount'
    :param mcs: MiniCloudStack instance with valid connection
    :param directory: Folder to unmount
    :param delete_after: True if you want directory to be deleted after unmounting
    """
    if not shell("umount {directory}".format(directory=directory)):
        raise minicloudstack.MiniCloudStackException(
            "Failed to unmount directory {}".format(directory))

    if delete_after:
        os.rmdir(directory)


def delete(mcs, volume_id, detach=True):
    """
    Delete volume.  This is an irreversible action.
    :param mcs: MiniCloudStack instance with valid connection
    :param volume_id: id of volume
    :param detach: True if volume needs to be detached first.
    :return:
    """
    if detach:
        try:
            mcs.call("detach volume", id=volume_id)
        except minicloudstack.MiniCloudStackException:
            pass    # Ignoring failures (race to detach)

    mcs.call("delete volume", id=volume_id)


def find_cloudstack_volume(mcs, vm_id, device_id=None, volume_id=None):
    """
    Find a CloudStack volume that is mounted to 'vm_id' or safe to re-mount.
    You need to provide either 'device_id' or 'volume_id'.
    :param mcs: MiniCloudStack instance with valid connection
    :param vm_id: id of virtual machine
    :param device_id: id of device
    :param volume_id: id of volume
    :return: volume object or 'None'
    """
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


def find_mounted_volume_vm_id(mcs, volume_id):
    """
    Find the vm the volume is mounted to (or None if not mounted)
    The vm might not be running.
    :param mcs: MiniCloudStack instance with valid connection
    :param volume_id: id of volume
    :return: vm_id or 'None'
    """
    vm_id = None
    for v in mcs.list("volumes", id=volume_id):
        attached_vm = getattr(v, "virtualmachineid", None)
        if attached_vm is not None:
            if hasattr(v, "deviceid"):
                return attached_vm

    return vm_id


def _cmd_is_json_options(s):
    try:
        options = json.loads(s)
        return isinstance(options, dict)
    except ValueError:
        return False


def _cmd_parse_options(s):
    fstype = "ext4"
    volumeid = None
    if not _cmd_is_json_options(s):
        return s, fstype

    options = json.loads(s)
    for k in options.keys():
        if "fstype" in k.lower():
            fstype = options[k]
        elif "volumeid" in k.lower():
            volumeid = options[k]
    return volumeid, fstype


def _get_vm_id(args):
    vm_id = args.vmid
    if hasattr(args, "nodename"):
        if args.nodename != vm_id:
            out_warn("Different nodename [{}] than current [{}] specified".format(args.nodename, vm_id))
            vm_id = args.nodename
    return vm_id


def cmd_init(mcs, args):
    out_info("Initializing...")
    return cmd_success("Initialized")


def cmd_getvolumename(mcs, args):
    volume_id, _ = _cmd_parse_options(args.options)
    if not volume_id:
        return cmd_error("missing volumeID")
    out_info("Getting volume name for {}...".format(volume_id))
    return cmd_success(volume_name=volume_id)


def cmd_isattached(mcs, args):
    volume_id, _ = _cmd_parse_options(args.options)
    vm_id = _get_vm_id(args)
    out_info("Checking if {} is attached to {}...".format(volume_id, vm_id))
    try:
        mounted_vm_id = find_mounted_volume_vm_id(mcs, volume_id=volume_id)
        if mounted_vm_id and mounted_vm_id == vm_id:
            return cmd_success("Volume is attached", attached=True)
        return cmd_success("Volume is not attached", attached=False)
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Device isattached check failed: {}".format(e))


def cmd_create(mcs, args):
    vm_id = _get_vm_id(args)
    if _cmd_is_json_options(args.options):
        options = json.loads(args.options)
        size = options.get("size", "1g")
    else:
        size = args.options
    out_info("Creating volume of size {} in zone of VM {}...".format(size, vm_id))
    try:
        vol_id = create(mcs, size, vm_id=vm_id)
        return cmd_success("Created volume", volume=vol_id)
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Volume create failed: {}".format(e))


def cmd_delete(mcs, args):
    volume_id, _ = _cmd_parse_options(args.options)
    out_info("Deleting volume {}...".format(volume_id))
    try:
        mcs.call("delete volume", id=volume_id)
        return cmd_success("Deleted volume", volume=volume_id)
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Volume create failed: {}".format(e))


def cmd_attach(mcs, args):
    volume_id, _ = _cmd_parse_options(args.options)
    if not volume_id:
        return cmd_error("missing volumeID")
    vm_id = _get_vm_id(args)
    out_info("Attaching device for volume {} to VM {}...".format(volume_id, vm_id))
    try:
        volume = find_cloudstack_volume(mcs, vm_id, volume_id=volume_id)
        if not volume:
            return cmd_error("No matching volume found")

        if getattr(volume, "virtualmachineid", vm_id) != vm_id:
            # Already attached to another stopped VM.
            out_warn("Detaching from VM {} since that one is in Stopped state".format(volume.virtualmachineid))
            volume = mcs.obj("detach volume", id=volume.id)
        if not hasattr(volume, "deviceid"):
            volume = mcs.obj("attach volume", id=volume_id, virtualmachineid=vm_id)
        device_name = device_id_to_name(volume.deviceid)
        return cmd_success("Attached device successfully", device=device_name)
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Device attach failed: {}".format(e))


def cmd_waitforattach(mcs, args):
    out_info("Waiting for attach...")
    return cmd_attach(mcs, args)


def cmd_detach(mcs, args):
    device = args.device
    vm_id = _get_vm_id(args)
    volume = None
    try:
        # Support device being a volume-id
        volume = find_cloudstack_volume(mcs, vm_id, volume_id=device)
        out_info("Detaching attached volume {}...".format(device))
    except minicloudstack.MiniCloudStackException:
        pass

    try:
        if volume is None:
            if not is_block_device(device):
                return cmd_error("Device {} is not a block device".format(
                    device))
            device_id = device_name_to_id(device)
            out_info("Detaching device {} [{}] from VM {}...".format(
                device, device_id, vm_id))
            volume = find_cloudstack_volume(mcs, vm_id, device_id=device_id)
        if not volume:
            return cmd_error(
                "Volume not found while detaching device {} from VM {}".format(
                    device, vm_id))

        out_info("Detaching volume [{}]".format(volume.id))
        mcs.call("detach volume", id=volume.id)
        return cmd_success("Detached device successfully", volume=volume.id)
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Volume detach failed: {}".format(e))


def cmd_mountdevice(mcs, args):
    directory = args.target
    device = args.device
    volume_id, fs_type = _cmd_parse_options(args.options)
    vm_id = args.vmid
    if not volume_id:
        return cmd_error("missing volumeID")

    volume = find_cloudstack_volume(mcs, vm_id, volume_id=volume_id)
    if not volume:
        return cmd_error("No matching volume found while mounting")

    out_info("Mounting volume {} with device {} to {}".format(
        volume_id, device, directory))
    try:
        mount(mcs, volume, directory, fs_type)
        return cmd_success("Volume mounted successfully for {}".format(device))
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Failed to mount device: {}".format(e))


def cmd_mount(mcs, args):
    directory = args.target
    volume_id, fs_type = _cmd_parse_options(args.options)
    vm_id = args.vmid
    if not volume_id:
        return cmd_error("missing volumeID")

    volume = find_cloudstack_volume(mcs, vm_id, volume_id=volume_id)
    if not volume:
        return cmd_error("No matching volume found while mounting")

    out_info("Mounting volume {} to {}".format(volume_id, directory))
    try:
        mount(mcs, volume, directory, fs_type)
        return cmd_success("Volume mounted successfully for {}".format(directory))
    except minicloudstack.MiniCloudStackException as e:
        return cmd_error("Failed to mount device: {}".format(e))


def cmd_unmount(mcs, args):
    target = args.target

    out_info("Unmounting {}".format(target))
    if not shell("umount {target}".format(target=target)):
        return cmd_error("Failed to unmount")

    if os.path.isdir(target):
        out_info("Removing mount directory {}".format(target))
        os.rmdir(target)

    return cmd_success("Unmounted successfully: {}".format(target))


def main():
    parser = argparse.ArgumentParser(description="CloudStack Local Volume Management")
    minicloudstack.add_arguments(parser)

    current_node = platform.node()

    parser.add_argument("--logfile", help="Log file name")
    parser.add_argument("-z", "--zone", help="Name of zone (if not zone of current vm)")
    parser.add_argument("-n", "--vmid", default=current_node,
                        help="Virtualmachine ID to use")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    commands = parser.add_subparsers(dest='command',
                                     help="<command> --help for command arguments")

    init_parser = commands.add_parser("init", help="Initialize")
    init_parser.set_defaults(func=cmd_init)

    attach_parser = commands.add_parser("create", help="Create volume")
    attach_parser.add_argument("options", help="size (in GB or options in json format)")
    attach_parser.set_defaults(func=cmd_create)

    attach_parser = commands.add_parser("getvolumename", help="Get volume name")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=cmd_getvolumename)

    attach_parser = commands.add_parser("isattached", help="Check if volume is attached")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.add_argument("nodename", default=current_node, nargs="?", help="Optional name of node")
    attach_parser.set_defaults(func=cmd_isattached)

    attach_parser = commands.add_parser("delete", help="Delete volume")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=cmd_delete)

    attach_parser = commands.add_parser("attach", help="Attach volume")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.add_argument("nodename", default=current_node, nargs="?", help="Optional name of node")
    attach_parser.set_defaults(func=cmd_attach)

    attach_parser = commands.add_parser("waitforattach", help="Attach volume and wait")
    attach_parser.add_argument("device", help="Mount device")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=cmd_waitforattach)

    attach_parser = commands.add_parser("detach", help="Detach volume")
    attach_parser.add_argument("device", help="Mount device")
    attach_parser.add_argument("nodename", default=current_node, nargs="?", help="Optional name of node")
    attach_parser.set_defaults(func=cmd_detach)

    attach_parser = commands.add_parser("mountdevice", help="Mount device")
    attach_parser.add_argument("target", help="Target mount directory")
    attach_parser.add_argument("device", help="Mount device")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=cmd_mountdevice)

    attach_parser = commands.add_parser("mount", help="Mount volume")
    attach_parser.add_argument("target", help="Target mount directory")
    attach_parser.add_argument("options", help="volumeID (or options in json format)")
    attach_parser.set_defaults(func=cmd_mount)

    attach_parser = commands.add_parser("unmount", aliases=["unmountdevice"], help="Unmount")
    attach_parser.add_argument("target", help="Volume/device to unmount")
    attach_parser.set_defaults(func=cmd_unmount)

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
        if LOG_FILE:
            logging.basicConfig(
                filename=args.logfile, level=level, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        else:
            logging.basicConfig(level=level, format="%(message)s")

    try:
        mcs = minicloudstack.MiniCloudStack(args)
        return args.func(mcs, args)
    except Exception as e:
        error_message = "EXCEPTION: {}".format(e)
        logging.error(error_message)
        return cmd_error(error_message)


if __name__ == "__main__":
    exit(main())
