from setuptools import setup
import os

setup(
    name='Coronado',
    version='1.0',
    scripts=['coronado.py'],
    packages=['Coronado'],
    install_requires=
    [
        'tornado',
        'MySQL-python',
        'unittest2',
        'argparse',
        'argh',
        'argcomplete',
        'pika',
        'python-dateutil',
        'importlib'
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Helper library for Tornado applications')
