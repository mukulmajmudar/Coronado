#!/bin/bash
set -x
docker build -t $USER/coronado .
mkdir -p dist
docker run --rm \
    -e USERID=$EUID \
    -v `pwd`/dist:/root/Coronado/dist \
    $USER/coronado
