from setuptools import find_packages, setup

from os import path

EXCLUDE_FROM_PACKAGES = []
README = 'README.rst'
REQUIREMENTS = 'requirements.txt'
VERSION = 'VERSION'
PACKAGE_DATA = [README, REQUIREMENTS, VERSION]

here = path.abspath(path.dirname(__file__))
with open(path.join(here, README)) as f:
    long_description = f.read()

requires = []
with open(path.join(here, REQUIREMENTS)) as f:
    for l in f.readlines():
        req = l.split('#')[0].strip()
        if req:
            requires.append(req)

with open(path.join(here, VERSION)) as f:
    version = f.read().strip()

setup(
    name='minicloudstack',
    version=version,
    url='https://github.com/greenqloud/minicloudstack',
    author='Greenqloud',
    description='Minimal CloudStack Access Library and Utilities',
    keywords='cloudstack',
    long_description=long_description,
    license='Apache',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    packages=find_packages(exclude=EXCLUDE_FROM_PACKAGES),
    package_data={'': PACKAGE_DATA},
    include_package_data=True,
    install_requires=requires,
    scripts=[],
    entry_points={'console_scripts': [
        'minicloudstack = minicloudstack.mcs:main',
        'mcs-createzone = minicloudstack.createzone:main',
        'mcs-deletezone = minicloudstack.deletezone:main',
        'mcs-registertemplate = minicloudstack.registertemplate:main',
        'mcs-addhost = minicloudstack.addhost:main',
        'mcs-volume = minicloudstack.volume:main',
    ]},
)
