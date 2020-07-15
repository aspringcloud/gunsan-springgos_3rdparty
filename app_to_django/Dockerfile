FROM ros:melodic

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

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
    ros-melodic-diagnostic-updater \
    python-pip \
    python2.7 \
    python2.7-dev \
    && rm -rf /var/lib/apt/lists/*
# python2.7.. ros1 is python2

# install pm2
RUN curl -sL https://deb.nodesource.com/setup_12.x | sudo -E bash -
RUN apt-get install -y nodejs
RUN curl https://www.npmjs.com/install.sh | sudo sh
RUN npm install pm2 -g
# ref https://github.com/keymetrics/pm2-logrotate
RUN pm2 install pm2-logrotate && pm2 set pm2-logrotate:max_size 1K

#RUN apt-get update \
#    && apt-get add postgresql-dev gcc python2-dev musl-dev

# install dependencies
RUN pip3 --version && pip3 install --upgrade pip
RUN git clone -b master git://github.com/kennethreitz/requests.git && \
    cd /requests/ && \
    python setup.py install && \
    rm -rf /requests

RUN git clone -b master https://github.com/dpallot/simple-websocket-server.git \
    && cd simple-websocket-server \
    && python setup.py install \
    && rm -rf simple-websocket-server

# RUN apt-get update
ADD . /ws/src/app_to_django/
WORKDIR /ws                             
RUN pip2 install -r ./src/app_to_django/requirements.txt
RUN /bin/bash -c "source /ros_entrypoint.sh && catkin_make"
# 아래는 실행 안됨 docker-compose에서 volume을 설정하니 host의 volume이 덮어씌여짐.
CMD ["chmod",  "777", "/ws/src/app_to_django/src/websocket.py"]

