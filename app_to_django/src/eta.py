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


def main(config):
    rospy.init_node("eta", log_level=rospy.DEBUG, disable_signals=True)
    top = smach.StateMachine(outcomes=['succeeded', 'preempted', 'aborted'])
    top.userdata.blackboard = sp.init_blackboard()
    with top:
        smach.StateMachine.add('a', sp.preempted_timeout(config.duration), {'succeeded': 'a'})


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
