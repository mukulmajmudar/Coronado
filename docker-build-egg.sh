#!/bin/bash
tag=`git rev-parse --abbrev-ref HEAD`
set -x
docker rm coronado-$tag-build > /dev/null 2> /dev/null
docker build -t coronado:$tag-build .
mkdir -p dist
docker run --name=coronado-$tag-build \
    -v `pwd`/dist:/root/Coronado/dist coronado:$tag-build
