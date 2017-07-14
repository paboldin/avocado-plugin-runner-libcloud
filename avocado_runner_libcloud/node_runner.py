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
# Copyright: Cloud Linux, 2017
# Authors: Pavel Boldin <pboldin@cloudlinux.com>
#
# Copyright: Red Hat Inc. 2014-2017
# Authors: Ruda Moura <rmoura@redhat.com>
#          Cleber Rosa <crosa@redhat.com>
import getpass
import os
import random
import string

import functools
from avocado.core.settings import settings
from avocado.core.settings import SettingsError
from libcloud.common.types import LibcloudError
from libcloud.compute import providers
from libcloud.compute.types import Provider

NODE_NAME_TEMPLATE = 'avocado-{username}-{uid}'


def _username_from_repo(repo_path):
    try:
        import git
        repo = git.Repo(path=repo_path, search_parent_directories=True)
        username = repo.config_reader().get('user', 'email')
    except:
        username = None
    return username


def _get_username():
    try:
        username = settings.get_value('libcloud', 'username', None)
    except SettingsError:
        username = None
    # try to get username from test repository
    username = username or _username_from_repo(os.getcwd())
    # try to get username from avocado_runner_libcloud repository
    username = username or _username_from_repo(__file__)
    # fallback to username in system
    username = username or getpass.getuser()

    username = username.replace('@', '-at-')
    username = username.replace('.', '--')

    return username


def _generate_instance_name():
    # random component
    rnd = random.SystemRandom()
    uid = ''.join(rnd.sample(string.ascii_lowercase + string.digits, 8))
    username = _get_username()
    return NODE_NAME_TEMPLATE.format(username=username, uid=uid)


__node_runner_register = dict()


def register(provider_name, provider=None):
    if provider is None:
        return functools.partial(register, provider_name)
    __node_runner_register[provider_name] = provider
    return provider


def get_node_runner(provider_name, *args, **kwargs):
    node_runner_cls = __node_runner_register[provider_name]
    return node_runner_cls(*args, **kwargs)


class NodeRunnerBase(object):
    """
    Base class that handles command line arguments
    and creates libcloud node.
    """
    provider = None

    def __init__(self, cli_args, wait_timeout=60, wait_period=3, ssh_interface='public_ips'):
        self.cli_args = cli_args
        self.wait_timeout = wait_timeout
        self.wait_period = wait_period
        self.ssh_interface = ssh_interface
        self.driver = self.create_driver()

    def create_driver(self):
        args, kwargs = self.get_driver_arguments()
        driver_class = providers.get_driver(self.provider)
        return driver_class(*args, **kwargs)

    def create_node(self):
        args, kwargs = self.get_node_arguments()
        return self._create_node(*args, **kwargs)

    def get_node_arguments(self):
        args = []
        kwargs = {
            'name': self.cli_args.libcloud_name or self.generate_name(),
            'size': self.cli_args.libcloud_size,
            'image': self.cli_args.libcloud_image_id,
        }
        return args, kwargs

    def get_driver_arguments(self):
        args = [self.cli_args.libcloud_client_id,
                self.cli_args.libcloud_client_key]
        kwargs = {}
        return args, kwargs

    def generate_name(self):
        return _generate_instance_name()

    def _create_node(self, *args, **kwargs):
        node = self.driver.create_node(*args, **kwargs)
        node, dummy = self.driver.wait_until_running(nodes=[node],
                                                     wait_period=self.wait_period,
                                                     timeout=self.wait_timeout,
                                                     ssh_interface=self.ssh_interface)[0]
        return node


@register('GCE')
class GoogleComputeEngineNodeRunner(NodeRunnerBase):
    provider = Provider.GCE

    def get_driver_arguments(self):
        args, kwargs = super(GoogleComputeEngineNodeRunner, self).get_driver_arguments()
        kwargs['project'] = self.cli_args.libcloud_gce_project
        return args, kwargs

    def get_node_arguments(self):
        args, kwargs = super(GoogleComputeEngineNodeRunner, self).get_node_arguments()

        kwargs['location'] = self.cli_args.libcloud_zone
        if self.cli_args.libcloud_key_file:
            with open(self.cli_args.libcloud_key_file, 'r') as fh:
                key = '%s:%s' % (self.cli_args.libcloud_username, fh.read())
            kwargs['ex_metadata'] = {'ssh-keys': key}

        return args, kwargs


@register('DIGITAL_OCEAN')
class DigitalOceanNodeRunner(NodeRunnerBase):
    provider = Provider.DIGITAL_OCEAN

    def get_node_arguments(self):
        args, kwargs = super(DigitalOceanNodeRunner, self).get_node_arguments()
        opts = self.cli_args

        def filter_by_id(items, id_or_name):
            found = [x for x in items if id_or_name in (x.name, x.id)]
            if not found:
                return None, ", ".join([getattr(x, 'name', getattr(x, 'id', None))
                                        for x in items])
            return found[0], None

        location, locations = filter_by_id(self.driver.list_locations(),
                                           opts.libcloud_zone)
        if not location:
            raise LibcloudError("Can't find location: %s, known: %s" %
                                (opts.libcloud_zone, locations))

        kwargs['location'] = location

        size, sizes = filter_by_id(self.driver.list_sizes(),
                                   opts.libcloud_size)
        if not size:
            raise LibcloudError("Can't find size: %s, known: %s" %
                                (opts.libcloud_size, sizes))
        kwargs['size'] = size

        image, images = filter_by_id(self.driver.list_images(),
                                     opts.libcloud_image_id)
        if not image:
            raise LibcloudError("Can't find image: %s, known: %s" %
                                (opts.libcloud_image_id, images))
        kwargs['image'] = image

        if opts.libcloud_key_file:
            try:
                key = self.driver.get_key_pair(name=_get_username())
            except Exception:
                with open(opts.libcloud_key_file, "r") as fh:
                    key = self.driver.create_key_pair(_get_username(),
                                                      fh.read())
            kwargs['ex_ssh_key_ids'] = [key.extra['id']]

        return args, kwargs
