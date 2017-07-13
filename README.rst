Avocado Libcloud runner
=======================

Run your nice avocado-powered tests on any Cloud supported by libcloud.

Installation
------------

Install the avocado with the optional plugin
``optional_plugins/runner_remote`` as described `here
<http://avocado-framework.readthedocs.io/en/latest/GetStartedGuide.html#installing-avocado>`__.

Checkout the repo and run ``setup.py``:

.. code:: shell

        $ git clone https://github.com/paboldin/avocado-plugin-runner-libcloud
        ...
        $ cd avocado-plugin-runner-libcloud
        $ python setup.py install # prefix with `sudo` if necessary
        or
        $ python setup.py develop --prefix=~/.local # for local development install


Use it now, for instance, with the Google Compute Engine:

.. code:: shell

        $ avocado run --libcloud-provider GCE                           \
        --libcloud-client-id  <YOUR_GCE_CLIENT_ID>                      \
        --libcloud-client-key <YOUR_GCE_CLIENT_KEY>                     \
        --libcloud-gce-project <YOUR_GCE_PROJECT>                       \
        --libcloud-key-file <YOUR_PUBLIC_SSH_KEY_PATH>                  \
        --libcloud-zone us-east1-b                                      \
        --libcloud-image-id ubuntu-1604-xenial-v20170619a               \
        --libcloud-size n1-standard-2 /bin/true


Most of the credentials should go into your ``~/.config/avocado/avocado.conf``
file. These set default values for command line arguments:

.. code:: ini

        [libcloud]
        provider=...
        client-id=...
        client-key=...
        key-file=...
        gce-project=...
