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
import collections
import json
import os
import re
import time

from . import requester

DEFAULT_JOBID_WAIT_COUNT = 60    # 60 * 5s == 5 minutes
VERBOSE = 0

LIST_INDEX_RE = re.compile(r"(.+)\[(\d+)\]")


def set_verbosity(verbosity=0):
    """
    Increase verbosity of functions.
    :param verbosity: 0=low, 1=details, 2=very verbose, 3=debug
    """
    global VERBOSE
    VERBOSE = int(verbosity)


def get_verbosity():
    """
    See 'set_verbosity()'
    :return: level of verbosity 0..N
    """
    return VERBOSE


class MiniCloudStackException(Exception):
    pass


Configuration = collections.namedtuple(
    "Configuration",
    "url apikey secretkey verifysslcert"
)


def get_env_defaults():
    """
    Tries to read default configuration from the following environment variables:
        CS_API_URL
        CS_API_KEY
        CS_SECRET_KEY
        CS_SSL_NO_VERIFY (optional)
    :return: Configuration instance
    """
    return Configuration(
        url=os.environ.get("CS_API_URL", os.environ.get("CS_URL", "")),
        apikey=os.environ.get("CS_API_KEY", ""),
        secretkey=os.environ.get("CS_SECRET_KEY", ""),
        verifysslcert=not (os.environ.get("CS_SSL_NO_VERIFY", "").strip().lower() in [
            "true", "yes", "1"
        ])
    )


def add_arguments(parser, defaults=None):
    """
    Add required connection arguments
    :param parser: ArgumentParser instance
    :param defaults: Configuration instance with defaults or 'None'
    """
    if not defaults:
        defaults = get_env_defaults()

    cs = parser.add_argument_group(
            "Connection",
            "CloudStack connection options (environment variable name).")
    cs.add_argument("-u", "--url", default=defaults.url, required=(len(defaults.url) == 0),
                    help="url to cloudstack api server (CS_API_URL)")
    cs.add_argument("-a", "--apikey", default=defaults.apikey, required=(len(defaults.apikey) == 0),
                    help="API Key (CS_API_KEY)")
    cs.add_argument("-s", "--secretkey", default=defaults.secretkey, required=(len(defaults.secretkey) == 0),
                    help="Secret Key (CS_SECRET_KEY)")
    cs.add_argument("--verifysslcert", action="store_true", default=defaults.verifysslcert,
                    help="Validate SSL certificates")


class MiniCloudStack(object):
    def __init__(self, args=None):
        """
        Initialize connection to cloudstack.  See add_arguments for help adding those to your program.
        :param args: object with connection arguments (url, apikey, secretkey)
                    if empty uses 'get_env_defaults()'
        """
        if not args:
            args = get_env_defaults()

        if not len(args.url) or not len(args.apikey) or not len(args.secretkey):
            raise MiniCloudStackException("Missing connection arguments (or environment variables)")

        self._creds = {
            "apikey": args.apikey,
            "secretkey": args.secretkey
        }
        self._url = args.url
        self._verifysslcert = args.verifysslcert

        # Trigger first call to check credentials
        self._capability = self.obj("list capabilities")

    def obj(self, api, **kwargs):
        """
        Call cloudstack API 'api' that returns one object
        :param api: api name, e.g. listCapabilities (or 'list capabilities')
        :param kwargs: arguments required for api call
        :return: result as MCSResult object (access members as obj.member)
        """
        result = self.call(api, **kwargs)
        if len(list(result.keys())) == 2 and "count" in result:
            from_list = True
            count = result.pop("count")
        else:
            from_list = False
            count = len(list(result.keys()))
        if count != 1:
            raise MiniCloudStackException("obj only supports api calls that return one item")
        key, value = result.popitem()
        if from_list:
            assert isinstance(value, list) and len(value) == 1
            value = value[0]
        if VERBOSE > 1:
            print("OBJ: {}={}".format(key, value))
        return MCSResult(value)

    def list(self, object_type, **kwargs):
        """
        Call CoudStack list* API function
        :param object_type: api object (e.g. 'clusters', 'image stores')
        :param kwargs: additional api arguments
        :return: python list object with results
        """
        items = []
        result = self.call("list " + object_type, **kwargs)
        if result:
            lower_case = "".join(object_type.split()).lower()
            singular = guess_singular(lower_case)
            for item in peel(result, singular):
                items.append(MCSResult(item))

        return items

    def map(self, object_type, unique_key="id", **kwargs):
        """
        Call CloudStack and return result in hash map (for list* api functions)
        :param object_type: api object (e.g. 'clusters', 'image stores')
        :param unique_key: unique key used for hash map
        :param kwargs: additional api arguments
        :return: hash map with result objects
        """
        m = {}
        items = self.list(object_type, **kwargs)
        for i in items:
            m[i._raw[unique_key]] = i

        return m

    def delete(self, object_type, **kwargs):
        """
        TODO: Document
        :param object_type:
        :param object_id:
        :param confirm_deleted:
        :param kwargs:
        :return:
        """
        result = self.call("delete " + object_type, **kwargs)
        return result

    def version(self):
        """
        :return: Cloudstack version in major,minor form (.e.g 4,2)
        """
        version = self._capability.cloudstackversion
        components = version.split(".")
        if len(components) < 2:
            raise MiniCloudStackException("Failed to get cloudstack version ({})".format(version))
        return components[0], components[1]

    def call(self, api, **kwargs):
        """
        Call cloudstack API 'api'
        :param api: api name, e.g. listCapabilities (or 'list capabilities')
        :param kwargs: arguments required for api call
        :return: result as dict (use 'peel' to find items)
        """
        result = self._call_api_internal(api, **kwargs)

        if "jobid" in result:
            jobid = peel(result, ".jobid")
            if VERBOSE > 1:
                print("Waiting for job {} to be finished".format(jobid))
            retries = DEFAULT_JOBID_WAIT_COUNT
            sleep_time = 1  # first one is 1s
            while retries:
                result = self._call_api_internal("query async job result", jobid=jobid)
                if VERBOSE > 1:
                    print("job {} status: {}".format(jobid, result))
                jobstatus = peel(result, ".jobstatus")
                if jobstatus == 0:
                    retries -= 1
                    time.sleep(sleep_time)
                    sleep_time = 5  # subsequent sleeps are 5s
                elif jobstatus == 1:
                    # Success
                    if peel(result, ".jobresulttype") == "object":
                        result = peel(result, ".jobresult")
                    break
                else:
                    error_code = peel(result, ".jobresult.errorcode")
                    error_str = peel(result, ".jobresult.errortext")
                    raise MiniCloudStackException("Failed to process '{}' [{}]: {}".format(api, error_code, error_str))

        return result

    def _call_api_internal(self, api, **kwargs):
        api = api_function(api)
        unwrap_args = self._unwrap_args(kwargs)
        description = "{}({})".format(api, ", ".join(sorted(["{}={}".format(a, repr(b)) for a, b in unwrap_args.items()])))
        if VERBOSE:
            print("CALL:   {}".format(description))
        reqres, reqerror = requester.make_request(
            api, unwrap_args, self._url, self._creds, 0, verifysslcert=self._verifysslcert)
        if reqerror:
            raise MiniCloudStackException("Failed to run: {}: {}".format(description, reqerror))
        if VERBOSE > 1:
            print("RESULT: {}".format(reqres))
        try:
            rdict = json.loads(reqres)
            k, v = rdict.popitem()
            # (sigh) api response does not always match request:
            #   enable storagemaintenance -> prepareprimarystorageformaintenanceresponse
            if k.endswith("response"):
                return v
            raise MiniCloudStackException("Response not found in result")
        except Exception:
            raise MiniCloudStackException("Response has invalid format: {}".format(reqres))

    def _unwrap_args(self, args):
        """
        Magical unwrapping of arguments to support cloudstack 'map' argument type
        :return: args  unchanged but list of map objects flattened out to item[index].property=stuff format
        """
        result = {}
        for k, v in args.items():
            if isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    for index, item in enumerate(v):
                        for ik, iv in item.items():
                            new_name = "{arg}[{index}].{field}".format(arg=k, index=index, field=ik)
                            result[new_name] = iv
                else:
                    if len(v) > 0:
                        result[k] = ",".join(v)
            elif isinstance(v, dict):
                index=0
                for ik,iv in v.items():
                    key_param = "{arg}[{index}].key".format(arg=k, index=index)
                    result[key_param] = ik
                    value_param = "{arg}[{index}].value".format(arg=k, index=index)
                    result[value_param] = iv
                    index = index+1
            else:
                result[k] = v
        return result


class MCSResult(object):
    def __init__(self, d):
        self._raw = d
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [MCSResult(x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, MCSResult(b) if isinstance(b, dict) else b)

    def __str__(self):
        return "MCSResult({})".format(", ".join(["{}={}".format(a, b) for a, b in self.as_dict().items()]))

    def as_dict(self):
        return self._raw


def api_function(name):
    """
    convert cloudmonkey like string to function name
    :param name: name
    :return: api function name
    """
    if " " in name:
        # start by converting 'images stores' to 'ImageStores'
        tc = "".join(name.title().split())
        # result key is lowercase version of this:
        return tc[0].lower() + tc[1:]
    else:
        return name


def peel(result, dotted):
    """
    Find field in dictionary.  Supports nesting (.foo.bar) and indexing (.smurf[3].cat)
    Borrows slightly from the syntax of 'jq'
    :param result: dictionary
    :param dotted: field name / path
    :return: data found
    """
    if dotted.startswith("."):
        dotted = dotted[1:]
    current = result
    for item in dotted.split("."):
        list_syntax = LIST_INDEX_RE.match(item)
        if list_syntax:
            item = list_syntax.group(1)
            index = int(list_syntax.group(2))

        # Workaround for issue with case not matching on elements <sigh>...
        item = item.lower()
        found = False
        obj = None
        for current_key, current_value in current.items():
            if current_key.lower() == item:
                obj = current_value
                found = True
                break
        if found:
            if list_syntax:
                assert isinstance(obj, list), "Key {} is not a list!?!".format(item)
                assert (index >= 0) and (index < len(obj)), \
                    "Index {} not in result set ({} has {} items)".format(index, item, len(obj))
                current = obj[index]
            else:
                current = obj
        else:
            raise MiniCloudStackException("Key {} not in result ({})".format(item, current))
    return current


def obj_if_exists(cs, type, **kwargs):
    results = cs.map(type, **kwargs)
    if len(results.keys()) > 1:
        print("Warning: more than one object found in {}".format(type))
    elif len(results.keys()) == 1:
        key, value = results.popitem()
        if VERBOSE:
            print("Found existing object {} with id {}".format(type, key))
        return value
    else:
        return None


def guess_singular(word):
    if word.endswith("ies"):
        return word[:-3] + "y"
    elif word[-3:] in ["ses", "xes", "zes"]:
        return word[:-2]
    elif word[-4:] in ["ches", "shes"]:
        return word[:-2]
    elif word.endswith("s"):
        return word[:-1]
    else:
        return word # wrong


class IpAddress(object):
    def __init__(self, dotted):
        self._dotted = dotted
        self._integer = 0
        for i in self._dotted.split("."):
            self._integer = self._integer*256 + int(i)

    def integer(self):
        return self._integer

    def binary(self):
        # > for correct endianness
        return "{:>032b}".format(self._integer)

    def dotted(self):
        return self._dotted

    def new_adding(self, addnum):
        """
        :param addnum: integer to add to this ip to create a new one (positive or negative)
        :return: new IpAddress (no range checking done)
        """
        return IpAddress.from_bits("{:>032b}".format(self._integer + addnum))

    def greater_than(self, ip_address):
        return self._integer > ip_address.integer()

    @classmethod
    def from_bits(cls, bits):
        i = 0
        for b in bits:
            i = i*2 + int(b)
        ip = []
        for q in range(4):
            ip.append(str(i % 0x100))
            i /= 0x100
        ip.reverse()
        return IpAddress(".".join(ip))


class IpCidr(object):
    def __init__(self, cidr):
        self._cidr = cidr
        addr, significant = cidr.split("/")
        self._ip = IpAddress(addr)
        self._significant = int(significant)
        bits = self._ip.binary()
        bits_unset = ""
        bits_set = ""
        bits_networmask = ""

        for b in range(0, 32):
            if b >= self._significant:
                bits_unset += "0"
                bits_set += "1"
                bits_networmask += "0"
            else:
                bits_unset += bits[b]
                bits_set += bits[b]
                bits_networmask += "1"

        self._firstip = IpAddress.from_bits(bits_unset)
        self._lastip = IpAddress.from_bits(bits_set)
        self._netmask = IpAddress.from_bits(bits_networmask)

    def cidr(self):
        return self._cidr

    def ip(self):
        return self._ip

    def firstip(self):
        return self._firstip

    def lastip(self):
        return self._lastip

    def netmask(self):
        return self._netmask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")

    add_arguments(parser)
    args = parser.parse_args()
    set_verbosity(args.verbose)
    mcs = MiniCloudStack(args)
    major, minor = mcs.version()
    print("Cloudstack version: {}.{}".format(major, minor))
    print(vars(mcs.obj("list capabilities")))

    print("")
    print("All zones:")
    for zone in mcs.list("zones"):
        print(zone.name, zone.id)

    print("")
    print("Fetching full API list:")
    api_desc = {}
    for a in mcs.list("apis"):
        api_desc[a.name] = a.description

    for name in sorted(api_desc.keys()):
        print("{:23}  {}".format(name, api_desc[name]))


if __name__ == "__main__":
    main()
