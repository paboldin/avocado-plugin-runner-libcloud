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

import os
import sys

from libcloud.common.types import LibcloudError

from avocado.core import exit_codes, exceptions
from avocado.core.output import LOG_UI
from avocado.core.plugin_interfaces import CLI
from avocado.core.settings import settings
from avocado_runner_remote import RemoteTestRunner

from avocado_runner_libcloud.node_runner import get_node_runner


class LibCloudTestRunner(RemoteTestRunner):
    """
    Test runner to run tests using libcloud compute
    """

    def __init__(self, job, result):
        super(LibCloudTestRunner, self).__init__(job, result)
        #: LibCloud Node used during testing
        self.node = None
        self.node_runner = get_node_runner(job.args.libcloud_provider,
                                           cli_args=job.args)

    def setup(self):
        """
        Initialize VM, establish connection and install avocado
        """

        args = self.job.args

        # Super called after VM is found and initialized
        self._job_log("PROVIDER   : %s", self.job.args.libcloud_provider)
        try:
            self.node = self._create_node()
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

        self._run_install_script()

    def tear_down(self):
        """
        Stop VM and restore snapshot (if asked for it)
        """
        if not self.job.args.libcloud_keep_node and self.node is not None:
            self.node.destroy()
            self.node = None

    def _job_log(self, *args):
        stdout_claimed_by = getattr(self.job.args, 'stdout_claimed_by', None)
        if not stdout_claimed_by:
            self.job.log.info(*args)

    def _run_install_script(self):
        module_dirname = os.path.dirname(os.path.realpath(__file__))
        avocado_install_script = os.path.join(module_dirname, 'avocado_install.sh')
        if not self.remote.send_files(avocado_install_script,
                                      '/tmp/avocado_install.sh'):
            raise exceptions.JobError("Can't copy avocado_install script")

        self._job_log("EXECUTING  : /tmp/avocado_install.sh")

        result = self.remote.run('sh -x /tmp/avocado_install.sh', quiet=False,
                                 ignore_status=True, timeout=120)
        if result.failed:
            self.job.log.error(result.stdout)
            self.job.log.error(result.stderr)
            raise exceptions.JobError("avocado installation failed")
        else:
            self.job.log.debug(result.stdout)
            self.job.log.debug(result.stderr)

    def _create_node(self):
        """
        Create LibCloud Node

        :param args: specific arguments
        :return: an instance of :class:`libcloud.Node`
        """
        return self.node_runner.create_node()


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
        # LOG_UI.error("%s %s" % (argument, kwargs))
        self.parser.add_argument(argument, **kwargs)

    def configure(self, parser):
        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        msg = 'test execution on a LibCloud compute'
        self.parser = run_subcommand_parser.add_argument_group(msg)
        self.add_argument('--libcloud-provider',
                          help='Specify LibCloud Provider')
        self.add_argument('--libcloud-client-id',
                          help='Specify LibCloud Client ID')
        self.add_argument('--libcloud-client-key',
                          help='Specify LibCloud Client key')
        self.add_argument('--libcloud-name', default=None,
                          help='Specify LibCloud compute name')
        self.add_argument('--libcloud-size', default=None,
                          help='Specify LibCloud size. Default: %(default)s')
        self.add_argument('--libcloud-image-id',
                          help='Specify LibCloud image ID.')
        self.add_argument('--libcloud-zone',
                          help='Specify LibCloud zone for some providers')
        self.add_argument('--libcloud-gce-project',
                          help='Specify LibCloud project for GCE provider')

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
        if self._check_required_args(
                args, 'libcloud_provider',
                ('libcloud_provider', 'libcloud_client_id',)):
            args.test_runner = LibCloudTestRunner
