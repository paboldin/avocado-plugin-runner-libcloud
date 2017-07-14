#!/bin/env python
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2017
# Author: Cleber Rosa <crosa@redhat.com>

from setuptools import setup, find_packages


setup(name='avocado-framework-plugin-runner-libcloud',
      description='Avocado Runner for libcloud VM Execution',
      version=open("VERSION", "r").read().strip(),
      author='Pavel Boldin',
      author_email='pboldin@cloudlinux.com',
      packages=find_packages(),
      include_package_data=True,
      install_requires=['avocado',
                        'avocado-framework-plugin-runner-remote',
                        'apache-libcloud'],
      entry_points={
          'avocado.plugins.cli': [
              'libcloud = avocado_runner_libcloud:LibCloudCLI',
          ]}
      )
