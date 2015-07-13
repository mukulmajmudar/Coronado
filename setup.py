from setuptools import setup
import os

setup(
    name='Coronado',
    version='2.0',
    scripts=['coronado.py'],
    packages=['Coronado', 'Coronado/RabbitMQ'],
    install_requires=
    [
        'tornado',
        'unittest2',
        'argparse',
        'argh',
        'argcomplete',
        'pika',
        'python-dateutil'
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Helper library for Tornado applications')
