from setuptools import setup, find_packages
import os

setup(
    name='Coronado',
    version='0.1',
    packages=['Coronado'],
    install_requires=
    [
        'tornado',
        'Twisted',
        'MySQL-python'
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Helper library for Tornado apps')
