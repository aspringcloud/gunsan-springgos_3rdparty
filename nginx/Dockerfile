FROM nginx
# RUN apt-get update && apt-get upgrade -y && apt-get -y install \ sudo
# WORKDIR /ws/src/cert/
# RUN RUN openssl rand -out /root/.rnd -hex 256
# RUN /bin/bash -c "openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout key.pem -subj '/C=kr/ST=Seoul/O=self-signed Cert/CN=:222.114.39.8'"
COPY nginx.conf /etc/nginx/conf.d/default.conf
# RUN /bin/bash -c "chown -R root:root /ws/cert.pem"
# RUN /bin/bash -c "chown -R root:root /ws/key.pem"
# RUN /bin/bash -c "chmod -R 600 /ws/src/cert/springgo.io_20200826SLZJ.crt.pem"
# RUN /bin/bash -c "chmod -R 600 /ws/src/cert/springgo.io_20200826SLZJ.key.pem"
# RUN /bin/bash -c "setsebool httpd_can_network_connect on -P"
