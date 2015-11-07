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
    PyMySQL \
    pika \
    python-dateutil \
    tornado \
    unittest2

RUN pip3 install logilab-common==0.63.0 pylint

COPY . /root/Coronado
WORKDIR /root/Coronado
ENTRYPOINT ["./entrypoint.sh"]
