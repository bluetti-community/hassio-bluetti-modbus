#!/bin/sh

# Execute unittests of python library inside docker
sudo docker build --progress=plain -t hassio-bluetti-modbus-tests -f Dockerfile.test .
