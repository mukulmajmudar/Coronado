from setuptools import setup

setup(
    name='Coronado',
    version='3.0',
    scripts=['coronado.py'],
    packages=['Coronado'],
    install_requires=
    [
        'argcomplete',
        'argh',
        'argparse'
    ],
    author='Mukul Majmudar',
    author_email='mukul@curecompanion.com',
    description='Simple application life cycle with plugin interface')
