#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# License: Unspecified
#

from __future__ import absolute_import, division, print_function
"""
Description
"""
import argparse
import os
import sys

import rospy
import smach
from smach import CBState
import states as sp


'''
app_to_django    | [DEBUG] [1592373107.677877]: gnss_latitude 35.836179
app_to_django    | [DEBUG] [1592373107.679026]: gnss_longitude 128.681446
app_to_django    | [INFO] [1592373107.680245]: site 2, station STA001, 17.038929m
app_to_django    | [INFO] [1592373107.688052]: site 2, station STA002, 643.894195m
app_to_django    | [INFO] [1592373107.689314]: site 2, station STA003, 781.124017m
app_to_django    | [INFO] [1592373107.690575]: site 2, station STA004, 490.352185m
'''


def show_description():
    return "Test ROS node"


def show_usage(cmd=None):
    cmd = os.path.relpath(sys.argv[0], os.getcwd()) if cmd is None else cmd
    return "{0} [-h|--help] [--version]".format(cmd)


def show_epilog():
    return "never enough testing"


def log(msg):
    pass


def main(config):
    rospy.init_node("eta", log_level=rospy.INFO, disable_signals=True)
    # smach.set_loggers(log,log,log,log) # disable
    top = smach.StateMachine(outcomes=['succeeded', 'preempted', 'aborted', 'timeout'])
    top.userdata.blackboard = sp.init_blackboard()
    with top:
        # smach.StateMachine.add('start', sp.post_eta_to_django(), {'succeeded': 'timeout'})

        # 1. 5초마다 eta 실행
        # 2. stationo에 eta post
        # 3. 1번 반복 
        smach.StateMachine.add('5sec', sp.preempted_timeout(5), {'succeeded': 'eta'})
        smach.StateMachine.add('eta', sp.make_eta_from_kafka_until_10min(), {'succeeded': '5sec'})
    
    '''
        smach.StateMachine.add('start', sp.get_station_from_django(), {'succeeded': 'make'})
        smach.StateMachine.add('make', sp.make_eta_from_kafka_until_10min(),
        {
            'succeeded': 'post',    #
            'timeout': 'check'      # 10min 초과하면 check_10houre로
        })
        smach.StateMachine.add('post', sp.post_eta_to_django_by_1sec(), {'succeeded': 'check'})
        smach.StateMachine.add('check', sp.check_10hour(),
        {
            'succeeded': 'make',        # 10시간 초과 안되면 make_from_kafka로
            'timeout': 'start'          # 10시간 초과하면 get_station
        })
    '''
    '''
        get_station_from_django()
        get_gnss_from_kafak 확인 필수
        extract gnss value, compare station position
        calcuration km
        post api .. 정의
    '''

    outcome = top.execute()
    rospy.signal_shutdown('done!')


if __name__=="__main__":
    args = rospy.myargv(sys.argv)
    print(args)
    # Ref : https://docs.python.org/2/library/argparse
    parser = argparse.ArgumentParser(description=show_description(),
                                     usage=show_usage(),
                                     epilog=show_epilog(),
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--version', action='store_true', help="display the version number and exits.")
    parser.add_argument('-t', '--timeout', type=int, default=10, help='send topic once every 60 seconds')
    parser.add_argument('-i', '--topic', type=str, default='/diagnostics', help='diagnostic topic to publish')
    parser.add_argument('-b', '--buffer', type=int, default=10, help='buffer size to republish the diagnostic data')
    parser.add_argument('-r', '--bitrate', type=int, default=3500, help='gst image size')
    parser.add_argument('-a', '--host', type=str, default='192.168.0.221', help='host address to send')
    parser.add_argument('-p', '--port', type=int, default=5000, help='port to send using gst')
    parser.add_argument('-d', '--duration', type=int, default=30, help='rosbag quit time(second)')

    parsed_known_args, unknown_args = parser.parse_known_args(sys.argv[1:])
    if parsed_known_args.version:
        print("version " + sp.__version__ + "\n from " + sp.__file__)
        sys.exit(0)
    main(parsed_known_args)
