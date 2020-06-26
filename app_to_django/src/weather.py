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


def show_description():
    return "Test ROS node"


def show_usage(cmd=None):
    cmd = os.path.relpath(sys.argv[0], os.getcwd()) if cmd is None else cmd
    return "{0} [-h|--help] [--version]".format(cmd)


def show_epilog():
    return "never enough testing"

def get_weather_every_one_hour():
    t = smach.Sequence(outcomes=['succeeded', 'preempted', 'aborted'],
                          input_keys=['blackboard'], output_keys=['blackboard'], connector_outcome='succeeded')
    with t:
        smach.Sequence.add('get_weather_and_post', sp.get_weather_from_opensite_and_post())
        #smach.Sequence.add('get_dust_and_post', sp.get_dust_from_opensite_and_post())
        #smach.Sequence.add('post_django', sp.post_weather_to_django())
        smach.Sequence.add('wait_one_hour', sp.preempted_timeout(3600))
    return t

def main(config):
    rospy.init_node("eta", log_level=rospy.DEBUG, disable_signals=True)
    top = smach.StateMachine(outcomes=['succeeded', 'preempted', 'aborted', 'timeout'])
    top.userdata.blackboard = sp.init_blackboard()

    with top:
        smach.StateMachine.add('start', sp.get_site_from_django(), {'succeeded': 'weather'})
        smach.StateMachine.add('weather', get_weather_every_one_hour(),
        {
            'succeeded': 'check'
        })
        smach.StateMachine.add('check', sp.check_10hour(), 
        {
            'succeeded': 'weather',     # 10시간 초과 안되면 weahter
            'timeout': 'start'          # 10시간 초과하면 get site object from django
        })
    '''
        get weather every one hours
        post data to django
        repeat 
        if passed 10 houre: get_site_from_django
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
        print("version " + sp.__version__ +
              "\n from " + sp.__file__)
        sys.exit(0)
    main(parsed_known_args)
