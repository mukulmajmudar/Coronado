#!/bin/bash
tag=`git rev-parse --abbrev-ref HEAD`
set -x
docker rm $USER-coronado-$tag-build > /dev/null 2> /dev/null
docker build -t $USER/coronado:$tag-build .
mkdir -p dist
docker run --name=$USER-coronado-$tag-build \
    -v `pwd`/dist:/root/Coronado/dist $USER/coronado:$tag-build
