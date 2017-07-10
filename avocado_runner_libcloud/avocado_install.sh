#!/bin/sh -e

if test -n "$(command -v yum)"; then
	yum install -y python-pip git
elif test -n "$(command -v apt-get)"; then
	apt-get update
	apt-get install -y python-pip git
fi

pip install avocado-framework

git clone https://github.com/avocado-framework-tests/avocado-misc-tests/
