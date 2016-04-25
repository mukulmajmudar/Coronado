from setuptools import setup

setup(
    name='Coronado',
    version='2.0',
    scripts=['coronado.py'],
    packages=['Coronado'],
    install_requires=
    [
        'argcomplete',
        'argh',
        'argparse',
        'python-dateutil',
        'tornado>=4.3'
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Lifecycle and plugin framework for Tornado')
