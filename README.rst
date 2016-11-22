minicloudstack
==============

Makes it easy to connect to Apache CloudStack.  Tested with version 4.2 and later.

See: https://cloudstack.apache.org/

Includes helper scripts to work with zones and hosts and helps you get started with your own scripts.

Easiest is to set the following environment variables:

    export CS_API_URL="http://mycloudstackapi.example.com/"
    export CS_API_KEY="1235..."
    export CS_SECRET_KEY="abcdef..."

Or override using built in arguments.


Example usage
-------------
    # 1) Set your environment variables
    # 2) Start python (or ipython).
    import minicloudstack
    mcs = minicloudstack.MiniCloudStack()
    for template in mcs.list("templates", templatefilter="featured"):
        print template.id, template.name


Helper scripts
--------------
Also provider are the following scripts that can be useful:

    mcs-createzone
    mcs-deletezone
    mcs-registertemplate
    mcs-addhost
    minicloudstack

Start them with --help for detailed instructions.


Background
----------
These scripts where created by Greenqloud (see: https://www.greenqloud.com/ ).

The scripts where used in development of Qstack ( see: https://qstack.com/ ) but can be used with any CloudStack server.

We hope you find them useful!

Greenqloud Dev Team.
