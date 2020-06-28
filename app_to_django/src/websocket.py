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
from SimpleWebSocketServer import WebSocket, SimpleWebSocketServer, SimpleSSLWebSocketServer

from threading import Thread
import time
import json
import logging
import Queue
import ssl
from smach import CBState

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s (%(threadName)-2s) %(message)s',)
clients = []  # connections = {} 동일한 역할


class Connection(WebSocket):

    def __init__(self, server, sock, address):
        WebSocket.__init__(self, server, sock, address)
        self.player = None
        self.queue = None

    def handleMessage(self):
        self.queue.put([self, "text", self.data])
        # for client in clients:
        #    if client != self:
        #        client.sendMessage(self.address[0] + u' - ' + self.data)


    def handleConnected(self):
        print (self.address, 'connected')
        # for client in clients:
        #    client.sendMessage(self.address[0] + u' - connected')
        clients.append(self)

    def handleClose(self):
        clients.remove(self)
        print (self.address, 'closed')
        # for client in clients:
        #    client.sendMessage(self.address[0] + u' - disconnected')


class Server(SimpleWebSocketServer):

    def __init__(self, queue, host, port, websocketclass):
        SimpleWebSocketServer.__init__(self, host, port, websocketclass)
        self.queue = queue

    def _constructWebSocket(self, sock, address):
        connection = self.websocketclass(self, sock, address)
        connection.queue = self.queue
        return connection


class ThreadServer(Thread):

    def __init__(self, queue, host, port):
        Thread.__init__(self)
        self.queue = queue
        self.host = host
        self.port = port

    def run(self):
        self.server = Server(self.queue, self.host, self.port, Connection)
        self.server.serveforever()

    def get_all_connections(self):
        return self.server.connections.values()


class WebServer:
    """
    Creates a SimpleWebSocketServer on a new thread
    """
    def __init__(self):
        self.server = None
        self.server_thread = None

    def start(self):
        # self.server = SimpleSSLWebSocketServer('0.0.0.0', 9103, Connection,
        #    '/ws/src/app_to_django/cert.pem', '/ws/src/app_to_django/key.pem', ssl.PROTOCOL_TLSv1)
        self.server = SimpleWebSocketServer('0.0.0.0', 9103, Connection)
        self.server_thread = Thread(target=self.server.serveforever)
        self.server_thread.start()

    def get_all_connections(self):
        return self.server.connections.values()


def show_description():
    return "Test ROS node"


def show_usage(cmd=None):
    cmd = os.path.relpath(sys.argv[0], os.getcwd()) if cmd is None else cmd
    return "{0} [-h|--help] [--version]".format(cmd)


def show_epilog():
    return "never enough testing"


def loginfo(msg):
    logging.info(msg)


def logwarn(msg):
    logging.warning(msg)


def logdebug(msg):
    logging.debug(msg)


def logerr(msg):
    logging.error(msg)


def test123():
    t = smach.Sequence(outcomes=['succeeded', 'preempted', 'aborted'],
                          input_keys=['blackboard'], output_keys=['blackboard'], connector_outcome='succeeded')
    with t:
        smach.Sequence.add('0', sp.get_station_from_django())
        smach.Sequence.add('1', sp.preempted_timeout(3))
        smach.Sequence.add('2', sp.dummy())
        smach.Sequence.add('3', sp.post_to_django())
    return t


def main(config):
    # smach.set_loggers(loginfo,logwarn,logdebug,logerr) # disable
    rospy.init_node("websocket", log_level=rospy.DEBUG, disable_signals=True)

    # web_server = WebServer()
    # web_server.start()
    queue = Queue.Queue()

    server = ThreadServer(queue, '', 9103)
    server.setDaemon(True)
    server.start()

    top = smach.StateMachine(outcomes=['succeeded', 'preempted', 'aborted', 'timeout'])
    top.userdata.blackboard = sp.init_blackboard()
    with top:
        # smach.StateMachine.add('1', test123(), {'succeeded': 'consumer'})
        # smach.StateMachine.add('consumer', sp.consumer(), {'succeeded': 'consumer'})

        # smach.StateMachine.add('2', sp.preempted_timeout(100), {'succeeded': '2'})

        # 시작시 DB에서 vehicle, site 가져오고
        smach.StateMachine.add('start', sp.get_vehicle_site_from_django(), {'succeeded': 'ping'})
        # 클라 핑주고 
        smach.StateMachine.add('ping', sp.ping_to_clients(server), {'succeeded': 'msg'})
        # 10초 안에 웹소켓으로 데이터 들어 오면 vehicle, site정보 이용해서 보낸 클라제외하고 모든 클라한테 보낼 메시지 만들어 모두 전소
        smach.StateMachine.add('msg', sp.get_msg_until_sec(server, queue, 20),
        {
            'succeeded': 'post',    # 데이터가 들어오면 post로
            'timeout': 'check'       # 10초 초과시 ping으로
        })
        smach.StateMachine.add('post', sp.post_event_to_django(), {'succeeded': 'check'})
        # 무조건 거치고, 10시간 되면 vehicle, site DB에서 가져오고
        smach.StateMachine.add('check', sp.check_10hour(), 
        {
            'succeeded': 'ping',        # 10시간 초과 안되면 ping으로
            'timeout': 'start'          # 10시간 초과하면 API 호출
        })

    outcome = top.execute()
    rospy.signal_shutdown('done!')


if __name__ == "__main__":
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
    parser.add_argument('-d', '--duration', type=int, default=3, help='rosbag quit time(second)')

    parsed_known_args, unknown_args = parser.parse_known_args(sys.argv[1:])
    if parsed_known_args.version:
        print("version " + sp.__version__ + "\n from " + sp.__file__)
        sys.exit(0)
    main(parsed_known_args)
