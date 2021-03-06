FROM ros:melodic

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive

## Ensure UTF-8
RUN apt-get update && apt-get install -y locales
RUN locale-gen  en_US.UTF-8
ENV LANG        en_US.UTF-8
ENV LC_ALL      en_US.UTF-8

## UTC TIME -> KST
RUN ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime

# install psycopg2 dependencies
RUN apt-get update && apt-get upgrade -y && apt-get -y install \
    python3 \
    python3-dev \
    python3-pip \
    build-essential \
    cmake pkg-config \
    libpq-dev \
    gettext \
    sudo \
    ros-melodic-roslint \
    ros-melodic-smach \
    ros-melodic-smach-ros \
    ros-melodic-py-trees \
    ros-melodic-can-msgs \
    ros-melodic-diagnostic-updater 

# install pm2
RUN curl -sL https://deb.nodesource.com/setup_12.x | sudo -E bash -
RUN apt-get install -y nodejs
RUN curl https://www.npmjs.com/install.sh | sudo sh
RUN npm install pm2 -g
# ref https://github.com/keymetrics/pm2-logrotate
RUN pm2 install pm2-logrotate && pm2 set pm2-logrotate:max_size 1K

# install dependencies
RUN pip3 --version && pip3 install --upgrade pip
RUN git clone -b master git://github.com/kennethreitz/requests.git && \
    cd /requests/ && \
    python setup.py install && \
    rm -rf /requests

# RUN apt-get update
ADD . /ws/src/graph/
RUN pip3 install -r /ws/src/graph/requirements.txt
WORKDIR /ws/src/graph/graph_tutorial