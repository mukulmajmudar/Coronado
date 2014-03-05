from setuptools import setup
import os

setup(
    name='Coronado',
    version='0.1',
    packages=['Coronado'],
    install_requires=
    [
        'tornado',
        'MySQL-python',
        'unittest2',
        'argparse',
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Helper library for Tornado apps')
