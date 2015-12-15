#!/bin/bash
set -x
docker build -t $USER/coronado .
docker run --rm --entrypoint=pylint $USER/coronado Coronado
