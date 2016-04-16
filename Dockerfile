FROM centos:7

RUN echo "timeout=5" >> /etc/yum.conf && \
    yum update -y && \
    yum install -y epel-release

RUN yum install -y \
    gcc \
    make \
    openssl \
    openssl-devel \
    zlib-devel && \
        curl -O https://www.python.org/ftp/python/3.5.0/Python-3.5.0.tar.xz && \
        tar xf Python-3.5.0.tar.xz && \
        cd Python-3.5.0 && \
        ./configure && \
        make && \
        make install

# Install Coronado dependencies
RUN pip3 install \
    argparse \
    argh \
    argcomplete \
    pika \
    python-dateutil \
    tornado \
    unittest2

# Once Pylint 1.5.0 is released, replace this with "pip3 install pylint"
# https://bitbucket.org/logilab/pylint/issues/643/attributeerror-call-object-has-no
RUN yum install -y hg && \
    pip3 install \
        hg+https://bitbucket.org/logilab/astroid@1.4.0 \
        hg+https://bitbucket.org/logilab/pylint@1.5.0

WORKDIR /root/Coronado
ENTRYPOINT ["./entrypoint.sh"]
COPY . /root/Coronado
