#!/bin/bash

# if ! [[ "$(< /etc/alpine-release)" =~ '^3\.6\.' ]]
# then
#     echo "install.sh: Unsupported OS: only Alpine Linux 3.6.x is supported." >&2
#     exit 1
# fi

# Alpine does not use glibc, so pip disables binary wheels, therefore we also
# need SciPy dependencies.
sudo apk add \
    build-base bzip2 bzip2-dev cyrus-sasl-dev curl gfortran git haproxy \
    keyutils-dev lapack-dev libev-dev libevent-dev libffi-dev libressl \
    libressl-dev libuuid libxml2-dev libxslt-dev linux-headers openldap-dev \
    patch postgresql-dev python2 python2-dev suitesparse swig wget yaml-dev

curl https://bootstrap.pypa.io/get-pip.py | sudo python2.7
sudo python2.7 -m pip install -U setuptools virtualenv==15.1.0

python2.7 -m virtualenv .
source ./bin/activate
source ./_postinstall.sh
