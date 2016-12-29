from setuptools import find_packages, setup

from os import path

EXCLUDE_FROM_PACKAGES = []

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.rst')) as f:
    long_description = f.read()

setup(
    name='minicloudstack',
    version='1.0.3',
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
    include_package_data=True,
    install_requires=['requests-toolbelt>=0.7.0'],
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
