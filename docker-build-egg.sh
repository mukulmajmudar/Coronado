#!/bin/bash
tag=`git rev-parse --abbrev-ref HEAD`
set -x
docker build -t $USER/coronado:$tag-build .
mkdir -p dist
docker run --rm \
    -e USERID=$EUID \
    -v `pwd`/dist:/root/Coronado/dist \
    $USER/coronado:$tag-build
