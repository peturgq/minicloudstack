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
import base64
import hashlib
import hmac
import requests
import ssl
import sys

# Python 2 vs 3
try:
    from urllib.parse import quote_plus
except ImportError:
    from urllib import quote_plus

from datetime import datetime, timedelta
from requests_toolbelt import SSLAdapter

# Disable HTTPS verification warnings.
from requests.packages import urllib3
urllib3.disable_warnings()


def running_python2():
    return sys.version_info.major < 3


def encode_as_string(data):
    # Python 3 encode returns bytestring that requests does not like.
    result = ""
    for b in data.encode("utf-8"):
        result += chr(b)
    return result


def b64encode(data):
    if running_python2():
        return base64.encodestring(data)
    else:
        return base64.encodebytes(data).decode('ascii')


def make_request(command, args, url, credentials, expires,
                 verifysslcert=False, signatureversion=3):
    result = None
    error = None

    if not url.startswith('http'):
        error = "Server URL should start with 'http' or 'https', " + \
                "please check and fix the url"
        return None, error

    if not args:
        args = {}

    args = args.copy()
    args["command"] = command
    args["response"] = "json"
    signatureversion = int(signatureversion)
    if signatureversion >= 3:
        args["signatureversion"] = signatureversion
        if not expires:
            expires = 600
        expirationtime = datetime.utcnow() + timedelta(seconds=int(expires))
        args["expires"] = expirationtime.strftime('%Y-%m-%dT%H:%M:%S+0000')

    for key in args.keys():
        value = args[key]
        if running_python2():
            if isinstance(value, unicode):
                value = value.encode("utf-8")
        elif isinstance(value, str):
            value = encode_as_string(value)
        args[key] = value
        if not key:
            args.pop(key)

    def sign_request(params, secret_key):
        request = list(zip(params.keys(), params.values()))
        request.sort(key=lambda x: x[0].lower())
        hash_str = "&".join(
            ["=".join(
                [r[0].lower(),
                 quote_plus(str(r[1]), safe="*").lower()
                 .replace("+", "%20").replace("%3A", ":")]
            ) for r in request]
        )
        return b64encode(hmac.new(secret_key.encode("utf-8"), hash_str.encode("utf-8"),
                                  hashlib.sha1).digest()).strip()

    args['apiKey'] = credentials['apikey']
    args["signature"] = sign_request(args, credentials['secretkey'])

    session = requests.Session()
    session.mount('https://', SSLAdapter(ssl.PROTOCOL_TLSv1))

    try:
        response = session.get(url, params=args, verify=verifysslcert)

        result = response.text

        if response.status_code == 200:  # success
            error = None
        elif response.status_code == 401:      # auth issue
            error = "401 Authentication error"
        elif response.status_code != 200 and response.status_code != 401:
            error = "{0}: {1}".format(response.status_code,
                                      response.headers.get('X-Description'))
    except requests.exceptions.ConnectionError as e:
        return None, "Connection refused by server: %s" % e
    except Exception as pokemon:
        error = pokemon.message

    if error is not None:
        return result, error

    return result, error
