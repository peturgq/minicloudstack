#!/usr/bin/env python
#
# Copyright 2015 Greenqloud ehf
#
# hogni@greenqloud.com
#
# Register a new template
#

import minicloudstack

import argparse, MySQLdb, etcd, os
import re
import urllib
from urlparse import urlparse, parse_qs

verbose = 0

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

def update_database(newpxeurl, oldpxeurl):
    client = etcd.Client(host="localhost", port=2379)
    mysqlpw = client.read("/qstack/config/mysql/server_root_password").value

    db = MySQLdb.connect(host="localhost",
        user="root",
        passwd=str(mysqlpw),
        db="cloud")

    try:
        curb = db.cursor()
        curb.execute("update template_view set url=\"%s\" where url=\"%s\"" % (newpxeurl, oldpxeurl))
        curb.execute("update template_store_ref set url=\"%s\" where url=\"%s\"" % (newpxeurl, oldpxeurl))
        curb.close()
        db.commit()
        print "Database change successful"
    except MySQLdb.Error, e:
        db.rollback()
        print "Database update failed. Manual changes may be required"
        print e

def fix_template_pxe_url(pxeurl):
    if pxeurl.startswith("pxe:kernel"):
        urlparts=parse_qs(pxeurl)
        fixedpxeurl='pxe:kernel'"="+urllib.quote_plus(urlparts['pxe:kernel'][0])
        for param in urlparts:
            if param != 'pxe:kernel':      
                fixedpxeurl=fixedpxeurl+"&"+param+"="+urllib.quote_plus(urlparts[param][0])
        update_database(fixedpxeurl, pxeurl)

def copy_files_to_bootserver(pxeurl, image_url, ostype):
    try:
        if pxeurl.startswith("ks="):
            baremetalbase="/nfs/secondary1/baremetal"
            filename=image_url.split('/')[-1]
            filepath=baremetalbase+"/"+filename
            os.system("mkdir -p "+baremetalbase)
            os.system("wget "+image_url+ " -O "+filepath)
            os.system("tar -xf "+filepath+" --strip 1 -C "+baremetalbase+" root")
        else:
            tmpfile="/tmp/template.tar.bz2"
            os.system("ssh -o StrictHostKeyChecking=no qstack-baremetal wget "+image_url+ " -O "+tmpfile)
            os.system("ssh -o StrictHostKeyChecking=no qstack-baremetal tar -xf "+tmpfile+" --strip 1 -C / root")
            os.system("ssh -o StrictHostKeyChecking=no qstack-baremetal rm "+tmpfile)
            os.system("ssh -o StrictHostKeyChecking=no qstack-baremetal service apache2 reload")
            if ostype == 'windows':
                os.system("ssh -o StrictHostKeyChecking=no qstack-baremetal service smbd restart")

        print "File/s copied successfully"
    except Exception, e:
        print "Copying file/s failed for "+image_url
        print e

def create_template(arguments):
    cs = minicloudstack.MiniCloudStack(arguments)

    zone = obj_if_exists(cs, "zones", name=arguments.zonename)
    if not zone:
        print "Zone name doesn't exist. Exiting"
        exit(1)
    templates = obj_if_exists(cs, "templates", templatefilter="all", name=arguments.name)
    if templates:
        print "A template with that name already exists. Exiting"
        exit(1)

    ostype = None
    if arguments.ostype == "debian":
        ostype = obj_if_exists(cs, "os types", description="Debian GNU/Linux 7(64-bit)")
    elif arguments.ostype == "coreos":
        ostype = obj_if_exists(cs, "os types", description="CoreOS")
    elif arguments.ostype == "windows":
        ostype = obj_if_exists(cs, "os types", description="Windows Server 2012 (64-bit)")
    elif arguments.ostype == "centos":
        ostype = obj_if_exists(cs, "os types", description="Other CentOS (64-bit)")
    elif arguments.ostype == "rhel":
        # Until Red Hat Enterprise Linux ui bug gets fixed it needs to be registered as Other Linux
        ostype = obj_if_exists(cs, "os types", description="Other Linux (64-bit)")

    if not ostype:
        print "Couldn't find ostype. Exiting"
        exit(1)

    fixedpxeurl = None

    if arguments.ostype == "debian":
        pxeurl = "pxe:kernel=linux/debian8/linux&append=vga=normal console=ttyS0,115200n8 console=tty1 auto=true priority=critical choose_interface=auto initrd=linux/debian8/initrd.gz url=http://bootserver/linux/debian8/preseed.cfg"
        image_url = "http://repository.qstack.com/images/baremetal/baremetal-linux-debian8_1.0.tar.bz2"

    elif arguments.ostype == "coreos":
        pxeurl = "pxe:kernel=linux/coreos/coreos_production_pxe.vmlinuz&append=vga=normal console=ttyS0,115200n8 console=tty0 initrd=linux/coreos/coreos_production_pxe_image.cpio.gz"
        image_url = "http://repository.qstack.com/images/baremetal/baremetal-linux-coreos_1.0.tar.bz2"

    elif arguments.ostype == "windows":
        pxeurl = "pxe:kernel=windows/windows2012r2/undionly.0&append=vga=normal"
        image_url = "http://repository.qstack.com/images/baremetal/baremetal-windows-windows2012r2.tar.bz2"

    elif arguments.ostype == "centos":
        if arguments.templateurl:
            pxeurl = arguments.templateurl
        else:
            pxeurl = "pxe:kernel=linux/centos7/vmlinuz&append=vga=normal console=ttyS0,115200n8 console=tty1 initrd=linux/centos7/initrd.img ramdisk_size=10000 ks=http://bootserver/linux/centos7/kickstart.ks"
        image_url = "http://repository.qstack.com/images/baremetal/baremetal-linux-centos7.tar.bz2"

    elif arguments.ostype == "rhel":
        pxeurl = "pxe:kernel=linux/rhel7/vmlinuz&append=vga=normal console=ttyS0,115200n8 console=tty1 initrd=linux/rhel7/initrd.img ip=dhcp ks=http://bootserver/linux/rhel7/kickstart.ks"
        image_url = "http://repository.qstack.com/images/baremetal/baremetal-linux-rhel7.tar.bz2"



    template = cs.obj("register template",
                        name=arguments.name,
                        displaytext=arguments.name,
                        zoneid=zone.id,
                        hypervisor="BareMetal",
                        format="BareMetal",
                        ostypeid=ostype.id,
                        bits="64",
                        url=pxeurl,
                        ispublic=True,
                        isfeatured=True)
    if arguments.ostype == "debian":
        cs.call("update template", id=template.id, passwordenabled="true")
    #Centos not yet password enabled:
    #elif arguments.ostype == "centos":
    #    cs.call("update template", id=template.id, passwordenabled="true")

    print "Template successfully registered!"

    if template:
        if image_url:
           copy_files_to_bootserver(pxeurl, image_url, arguments.ostype)
        fix_template_pxe_url(pxeurl)

    print "Script ran successfully! You should now see your template in Qstack"

def main():
    global verbose

    parser = argparse.ArgumentParser("Register a BM template")

    parser.add_argument("-v",  "--verbose", action="count", help="Increase output verbosity")

    parser.add_argument("-n", "--name", help="Name of the template")
    parser.add_argument("-zn", "--zonename", required=True, help="Name of the zone to add template to")

    parser.add_argument("-ot", "--ostype", required=True, choices=["debian", "centos", "coreos", "windows", "rhel"],
                            help="Type of operating system to add")

    parser.add_argument("--templateurl", help="Optional template url")

    #parser.add_argument("-tpath", "--templatepath", required=False, help="Path to the template")
    #parser.add_argument("-tkern", "--templatekernel", required=False, help="Path to the template kernel")

    minicloudstack.add_arguments(parser)

    arguments = parser.parse_args()
    if not arguments.name:
       arguments.name = arguments.ostype+"-baremetal"

    verbose = arguments.verbose
    minicloudstack.set_verbosity(arguments.verbose)

    #if arguments.ostype == "debian" or arguments.ostype == "coreos":
    #    if not arguments.templatepath:
    #        print "You must specify both kernel AND image when using CoreOS/Debian"
    #        exit(1)

    try:
        create_template(arguments)
    except minicloudstack.MiniCloudStackException as e:
        if verbose > 1:
            raise e
        else:
            print " - - - "
            print "Error creating registering template:"
            print e.message

if __name__ == "__main__":
    main()
