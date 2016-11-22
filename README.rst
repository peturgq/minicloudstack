minicloudstack
==============

Makes it easy to connect to Apache CloudStack.  Tested with version 4.2 and later.

For more information on CloudStack see:
.. CloudStack: https://cloudstack.apache.org/

Includes helper scripts to work with zones and hosts and helps you get started with your own scripts.

Alternatives
------------
This library makes it easy to create quick utilities for Operational and Development purposes.
For an interactive shell you should try cloudmonkey or shell scripting you can try cs.

.. cloudmonkey: https://pypi.python.org/pypi/cloudmonkey/
.. cs: https://pypi.python.org/pypi/cs

Installation
------------
    pip install minicloudstack


Quickstart
----------
Export the following environment variables (alternatively arguments can be used):

.. code:: bash
    export CS_API_URL="http://mycloudstackapi.example.com/"
    export CS_API_KEY="1235..."
    export CS_SECRET_KEY="abcdef..."


Start your python shell (python or ipython).

.. code:: python
    import minicloudstack
    mcs = minicloudstack.MiniCloudStack()
    for template in mcs.list("templates", templatefilter="featured"):
        print template.id, template.name


Helper scripts
--------------
Also provided are the following scripts that can be useful:

.. code:: bash
    mcs-createzone
    mcs-deletezone
    mcs-registertemplate
    mcs-addhost
    minicloudstack

Start them with --help for detailed instructions.


Background
----------
These scripts were created by Greenqloud (see: https://www.greenqloud.com/ ).

The scripts were used in development of Qstack ( see: https://qstack.com/ ) but can be used with any CloudStack server.

We hope you find them useful!

Greenqloud Dev Team.
