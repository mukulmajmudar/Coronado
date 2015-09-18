#!/bin/bash
python setup.py bdist_egg
chown -R $USERID dist
chgrp -R $USERID dist
