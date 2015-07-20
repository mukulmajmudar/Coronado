#!/bin/bash
tag=`git rev-parse --abbrev-ref HEAD`
set -x
docker rm $USER-coronado-$tag-pylint > /dev/null 2> /dev/null
docker build -t $USER/coronado:$tag-pylint .
docker run --name=$USER-coronado-$tag-pylint $USER/coronado:$tag-pylint \
    pylint Coronado
