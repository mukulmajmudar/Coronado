#!/bin/bash
tag=`git rev-parse --abbrev-ref HEAD`
set -x
docker build -t $USER/coronado:$tag-pylint .
docker run --rm $USER/coronado:$tag-pylint pylint Coronado
