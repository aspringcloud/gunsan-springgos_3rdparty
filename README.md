

## install docker
* 
## install docker-compose
* 
# the app_to_django package
## build package
```bash
docker-compouse build
```
## run package
```bash
docker-compose up -d 
```
## usage examples
```bash
docker-compose exec app_to_django /bin/bash -c "source /ros_entrypoint.sh && rosnode list && pm2 logs"
docker-compose logs -f --tail=100 
```