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
import logging
import os
import random
import string
import sys
import time
from xml.dom import minidom

from libcloud.common.types import LibcloudError
import libcloud.compute.types as lctypes
import libcloud.compute.providers as lcproviders

from avocado.core import exit_codes, exceptions
from avocado.core.output import LOG_UI
from avocado.core.plugin_interfaces import CLI
from avocado.core.settings import settings
from avocado_runner_remote import Remote, RemoteTestRunner


NODENAME_TEMPLATE = 'avocado-{username}-{uid}'

def _get_username():
    try:
        import git
        repo = git.Repo(path=__file__, search_parent_directories=True)
        username = repo.config_reader().get('user', 'email')
    except Exception:
        username = getpass.getuser()

    username = username.replace('@', '-at-')
    username = username.replace('.', '--')

    return username

def _generate_name():
    # random component
    rnd = random.SystemRandom()
    uid = ''.join(rnd.sample(string.ascii_lowercase + string.digits, 8))

    username = None
    try:
        username = settings.get_value('libcloud', 'username', None)
    except Exception:
        pass
    if username is None:
        username = _get_username()

    return NODENAME_TEMPLATE.format(username=username, uid=uid)

# TODO(pboldin): use polymorphism for that
def _update_digital_ocean(opts, driver, kwargs):

    def filter_by_id(items, id_or_name):
        found = [x for x in items if x.id == id_or_name or x.name == id_or_name]
        if not found:
            return None, ", ".join([getattr(x, 'name', getattr(x, 'id', None))
                                    for x in items])
        return found[0], None

    location, locations = filter_by_id(
            driver.list_locations(),
            opts.libcloud_zone)
    if not location:
        raise LibcloudError("Can't find location: %s, known: %s" %
                            (opts.libcloud_zone, locations))

    kwargs['location'] = location

    size, sizes = filter_by_id(
            driver.list_sizes(),
            opts.libcloud_size)
    if not size:
        raise LibcloudError("Can't find size: %s, known: %s" %
                            (opts.libcloud_size, sizes))
    kwargs['size'] = size

    image, images = filter_by_id(
            driver.list_images(),
            opts.libcloud_image_id)
    if not image:
        raise LibcloudError("Can't find image: %s, known: %s" %
                            (opts.libcloud_image_id, images))
    kwargs['image'] = image

    if opts.libcloud_key_file:
        try:
            key = driver.get_key_pair(name=_get_username())
        except Exception:
            with open(opts.libcloud_key_file, "r") as fh:
                key = driver.create_key_pair(_get_username(),
                                             fh.read())
        kwargs['ex_ssh_key_ids'] = [ key.extra['id'] ]

def _update_gce(opts, driver, kwargs):
    kwargs['location'] = driver.zone_dict[opts.libcloud_zone]

    if opts.libcloud_key_file:
        with open(opts.libcloud_key_file, 'r') as fh:
            key = '%s:%s' % (opts.libcloud_username, fh.read())
        kwargs['ex_metadata'] = {'ssh-keys': key}

def libcloud_create_node(opts):
    """
    Create LibCloud Node

    :param args: specific arguments
    :return: an instance of :class:`libcloud.Node`
    """

    try:
        driver_cls = lcproviders.get_driver(
                getattr(lctypes.Provider, opts.libcloud_provider))
    except AttributeError:
        raise LibcloudError("Can't find libcloud provider %s" %
                opts.libcloud_provider)

    args = (opts.libcloud_client_id, opts.libcloud_client_key)
    kwargs = {}

    if opts.libcloud_provider == 'GCE':
        kwargs['project'] = opts.libcloud_gce_project

    driver = driver_cls(*args, **kwargs)

    kwargs = {
            'name': opts.libcloud_name or _generate_name(),
            'size': opts.libcloud_size,
            'image': opts.libcloud_image_id,
    }

    if opts.libcloud_provider == 'GCE':
        _update_gce(opts, driver, kwargs)

    if opts.libcloud_provider == 'DIGITAL_OCEAN':
        _update_digital_ocean(opts, driver, kwargs)

    node = driver.create_node(**kwargs)

    node, dummy = driver.wait_until_running(
            nodes=[node],
            wait_period=3,
            timeout=60,
            ssh_interface='public_ips')[0]

    return node

class LibCloudTestRunner(RemoteTestRunner):

    """
    Test runner to run tests using libcloud compute
    """

    def __init__(self, job, result):
        super(LibCloudTestRunner, self).__init__(job, result)
        #: LibCloud Node used during testing
        self.node = None

    def setup(self):
        """
        Initialize VM, establish connection and install avocado
        """

        args = self.job.args

        # Super called after VM is found and initialized
        stdout_claimed_by = getattr(args, 'stdout_claimed_by', None)
        if not stdout_claimed_by:
            self.job.log.info("PROVIDER   : %s", args.libcloud_provider)

        try:
            self.node = libcloud_create_node(args)
        except LibcloudError as exception:
            raise exceptions.JobError(exception.message or str(exception))

        # If hostname wasn't given, let's try to find out the IP address
        libcloud_hostname = self.node.public_ips[0]
        if libcloud_hostname is None:
            e_msg = ("Could not find the IP address for VM '%s'." %
                     self.node.name)
            raise exceptions.JobError(e_msg)

        # Finish remote setup and copy the tests
        args.remote_hostname = libcloud_hostname
        args.remote_port = args.libcloud_port
        args.remote_username = args.libcloud_username
        args.remote_password = args.libcloud_password
        args.remote_key_file = args.libcloud_key_file
        args.remote_timeout = args.libcloud_timeout
        super(LibCloudTestRunner, self).setup()

        dirname = os.path.dirname(os.path.realpath(__file__))
        avocado_install_script = os.path.join(dirname, 'avocado_install.sh')
        if not self.remote.send_files(avocado_install_script,
                                      '/tmp/avocado_install.sh'):
            raise exceptions.JobError("Can't copy avocado_install script")

        if not stdout_claimed_by:
            self.job.log.info("EXECUTING  : /tmp/avocado_install.sh")

        result = self.remote.run('sh -x /tmp/avocado_install.sh', quiet=False,
                                 ignore_status=True, timeout=120)
        if result.failed:
            self.job.log.error(result.stdout)
            self.job.log.error(result.stderr)
            raise exceptions.JobError("avocado installation failed")
        else:
            self.job.log.debug(result.stdout)
            self.job.log.debug(result.stderr)

    def tear_down(self):
        """
        Stop VM and restore snapshot (if asked for it)
        """
        super(LibCloudTestRunner, self).tear_down()
        if (self.job.args.libcloud_keep_node is False and
                getattr(self, 'node', None) is not None):
            self.node.destroy()
            self.node = None


class LibCloudCLI(CLI):

    """
    Run tests on a LibCloud compute
    """

    name = 'libcloud'
    description = "LibCloud options for 'run' subcommand"

    def add_argument(self, argument, **kwargs):
        key = argument.replace('--libcloud-', '')
        default = settings.get_value(
                'libcloud', key, key_type=kwargs.get('type', str),
                default=kwargs.get('default', None))
        if default is not None:
            kwargs['default'] = default
        #LOG_UI.error("%s %s" % (argument, kwargs))
        self.parser.add_argument(argument, **kwargs)

    def configure(self, parser):
        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        msg = 'test execution on a LibCloud compute'
        self.parser = run_subcommand_parser.add_argument_group(msg)
        self.add_argument('--libcloud-provider',
                          help=('Specify LibCloud Provider'))
        self.add_argument('--libcloud-client-id',
                          help=('Specify LibCloud Client ID'))
        self.add_argument('--libcloud-client-key',
                            help=('Specify LibCloud Client key'))
        self.add_argument('--libcloud-name', default=None,
                          help=('Specify LibCloud compute name'))
        self.add_argument('--libcloud-size', default=None,
                          help=('Specify LibCloud size. Default: %(default)s'))
        self.add_argument('--libcloud-image-id',
                          help=('Specify LibCloud image ID.'))
        self.add_argument('--libcloud-zone',
                          help=('Specify LibCloud zone for some providers'))
        self.add_argument('--libcloud-gce-project',
                          help=('Specify LibCloud project for GCE provider'))

        self.add_argument('--libcloud-port',
                          default=22, type=int,
                          help=('Specify the SSH port number to login on '
                                'VM. Default: %(default)s'))
        self.add_argument('--libcloud-username', default='root',
                          help=('Specify the username to login on VM. '
                                'Default: %(default)s'))
        self.add_argument('--libcloud-password',
                          default=None,
                          help='Specify the password to login on VM')
        self.add_argument('--libcloud-key-file',
                          dest='libcloud_key_file', default=None,
                          help=('Specify an identity file with '
                                'a private key instead of a password '
                                '(Example: .pem files from Amazon EC2)'))
        self.add_argument('--libcloud-keep-node', default=False)
        self.add_argument('--libcloud-timeout', metavar='SECONDS',
                          default=120, type=int,
                          help=("Amount of time (in seconds) to "
                                "wait for a successful connection"
                                " to the libcloud VM. Defaults"
                                " to %(default)s seconds."))

    @staticmethod
    def _check_required_args(args, enable_arg, required_args):
        """
        :return: True when enable_arg enabled and all required args are set
        :raise sys.exit: When missing required argument.
        """
        if (not hasattr(args, enable_arg) or
                not getattr(args, enable_arg)):
            return False
        missing = []
        for arg in required_args:
            if not getattr(args, arg):
                missing.append(arg)
        if missing:
            LOG_UI.error("Use of %s requires %s arguments to be set. Please "
                         "set %s.", enable_arg, ', '.join(required_args),
                         ', '.join(missing))

            return sys.exit(exit_codes.AVOCADO_FAIL)
        return True

    def run(self, args):
        if self._check_required_args(args,
                'libcloud_provider', ('libcloud_provider', 'libcloud_client_id',)):
            args.test_runner = LibCloudTestRunner
