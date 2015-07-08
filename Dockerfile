FROM centos:7

RUN yum install -y python-setuptools

COPY . /root/Coronado
WORKDIR /root/Coronado
CMD ["python", "setup.py", "bdist_egg"]
