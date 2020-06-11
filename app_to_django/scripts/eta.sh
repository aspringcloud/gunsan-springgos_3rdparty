#!/usr/bin/env bash

until rosnode info rosout | grep Pid; do sleep 1; done
source /ws/devel/setup.bash
roslaunch app_to_django eta.launch