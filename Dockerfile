FROM centos:7

RUN yum update -y && \
    yum install -y epel-release

RUN yum install -y \
    gcc \
    mysql \
    mysql-devel \
    python-devel \
    python-setuptools

# Install Coronado dependencies
# (-Z flag because sometimes there were race conditions with the egg cache)
RUN easy_install -Z \
    argparse \
    argh \
    argcomplete \
    importlib \
    MySQL-python \
    pika \
    python-dateutil \
    tornado \
    unittest2

RUN easy_install pylint

COPY . /root/Coronado
WORKDIR /root/Coronado
CMD ["python", "setup.py", "bdist_egg"]
