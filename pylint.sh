#!/bin/bash
./bin/pylint -d invalid-name -d trailing-whitespace -d missing-docstring -d too-many-public-methods -d protected-access $1 $2
