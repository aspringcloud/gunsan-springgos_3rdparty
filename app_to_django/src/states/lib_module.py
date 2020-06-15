#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

"""
Description
"""
import py_trees
import smach
import time
import rospy
import std_srvs
import subprocess
import signal
import diagnostic_msgs.msg
import requests
import os
import roslaunch
import diagnostic_updater
from diagnostic_msgs.msg import DiagnosticStatus
import json
import Queue
#added 2020.06.15
from requests.auth import HTTPBasicAuth
import kafka
from geopy.distance import great_circle

'''
{
    when: timestamp
    where: site pk
    who: 호출한 앱의 이름
    what: request, response, event, error
    how: {
        type: passenger
        vehicle_id:
        vehicle_mid:
        current_passenger:
        accumulated_passenger:
    }
    how: {
        type: power
        vehicle_id:
        vehicle_mid:
        value: on/off
    }
    how: {
        type: parking
        vehicle_id:
        vehicle_mid:
        value: true/false
    }
    how: {
        type: drive
        vehicle_id:
        vehicle_mid:
        value: auto/normal
    }
    how: {
        type: door
        vehicle_id:
        vehicle_mid:
        value: true/false
    }
    how: {
        type: message
        vehicle_id:
        vehicle_mid:
        value: message
    }
    what: request
    how: {
        type: dispatch
        vehicle_id:
        vehicle_mid:
        ?
    }
}
'''
def init_blackboard():
    blackboard = py_trees.blackboard.Blackboard()
    blackboard.pid = None
    blackboard.message = {
        "version": 1,
        "when": time.time(),
        "where": 'sejong_datahub',
        "who": 'android app',
        "what": 'EVENT',  #REQ, RESP ,EVET, ERROR
        "how": {
            "type": 'PASSENGER', # 'POWER', 'DOOR'
            "vehicle_id": 6,
            "current_passenger": 1,
            "accumulated_passenger": 17
        }
    }
    return blackboard


class consumer(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

        self.broker = '175.203.98.23:9092'
        self.topic =  'sgs-kiosk-vehicle' # sim-vehicle
        self.group =  'sgs-nifi-consumer005'
        self.consumer = kafka.KafkaConsumer(self.topic,
                bootstrap_servers = [self.broker], group_id=self.group,
                enable_auto_commit=True, consumer_timeout_ms=600000 # 10min
                )


    def execute(self, ud):
        stations = None
        with open('/ws/src/app_to_django/stations.json') as json_file:
            stations = json.load(json_file)

        for msg in self.consumer:
            try:
                if not len(msg) or not len(msg.value):
                    continue
                packet = json.loads(msg.value) # string to dictionary
                lata = 0.0
                lona = 0.0
                latb = 0.0
                lonb = 0.0
                if 'message' in packet:
                    if 'gnss_latitude' in packet['message']:
                        rospy.logdebug('gnss_latitude %f', float(packet['message']['gnss_latitude']))
                        latb = float(packet['message']['gnss_latitude'])
                    if 'gnss_longitude' in packet['message']:
                        rospy.logdebug('gnss_longitude %f', float(packet['message']['gnss_longitude']))
                        lonb = float(packet['message']['gnss_longitude'])
                    for station in stations:
                        if station['site'] == 2:
                            lata = float(station['lat'])
                            lona = float(station['lon'])

                            a = (lata, lona)
                            b = (latb, lonb)
                            rospy.loginfo("site %d, station %s, %fm", station['site'], station['mid'], great_circle(a, b).m)

                rospy.logdebug(json.dumps(packet, indent=4, sort_keys=True))
            except UnicodeError:
                rospy.logerr("UnicodeError - OK")
                return 'succeeded'

        return 'succeeded'

class get_vehicle_site_from_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        try:
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            sites = requests.request(
                method='get',
                url='http://115.93.143.2:9103/api/sites',
                auth = auth_ones,
                verify= None,
                headers={'Content-type': 'application/json'}
            )
            vehicles = requests.request(
                method='get',
                url='http://115.93.143.2:9103/api/vehicles',
                auth = auth_ones,
                verify= None,
                headers={'Content-type': 'application/json'}
            )
            with open('/ws/src/app_to_django/vehicles.json', 'w') as json_file:
                json.dump(vehicles.json(), json_file)
            with open('/ws/src/app_to_django/sites.json', 'w') as json_file:
                json.dump(sites.json(), json_file)
        except:
            return 'aborted'
        return 'succeeded'


class get_station_from_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        try:
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            stations = requests.request(
                method='get',
                url='http://115.93.143.2:9103/api/stations',
                auth = auth_ones,
                verify= None,
                headers={'Content-type': 'application/json'}
            )
            with open('/ws/src/app_to_django/stations.json', 'w') as json_file:
                json.dump(stations.json(), json_file)
        except:
            return 'aborted'
        return 'succeeded'

class ping_to_clients(smach.State):
    def __init__(self, server):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.server = server

    def execute(self, ud):
        for client in self.server.get_all_connections():
            data = {'sent_time': time.time(),
                    'client': client.address,
                    'kind': 'ping'}
            client.sendMessage(json.dumps(data))
            rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))
        return 'succeeded'


class post_to_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
    def execute(self, ud):
        how = ud.blackboard.message['how']
        data = {}
        pk = None
        if 'vehicle_id' in how:
            pk = how['vehicle_id']
        if 'current_passenger' in how:
            data['passenger'] = how['current_passenger']
        if 'parking' in how:
            data['isparked'] = how['parking']
        if 'drive' in how:
            data['drive'] = how['drive']
        if 'door' in how:
            data['door'] = how['door']

        auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
        r = requests.request(
            method='patch',
            url='http://115.93.143.2:9103/api/vehicles/{}/'.format(pk),
            data = json.dumps(data),
            auth = auth_ones,
            verify= None,
            headers={'Content-type': 'application/json'}
        )
        if not r is None:
            if r.status_code != 200:
                res = r.reason
                rospy.logerr('patch/'+r.reason)
            else:
                rospy.loginfo(r.status_code)
        rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))

        return 'succeeded'

class dummy(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
    def execute(self, ud):
        start_time = time.time()

        vehicles = None
        sites = None
        with open('/ws/src/app_to_django/vehicles.json') as json_file:
            vehicles = json.load(json_file)
        with open('/ws/src/app_to_django/sites.json') as json_file:
            sites = json.load(json_file)
        sites = sites['results']
        for vehicle in vehicles:
            if isinstance(ud.blackboard.message['how']['vehicle_id'], str):
                ud.blackboard.message['how']['vehicle_id'] = int(ud.blackboard.message['how']['vehicle_id'])
            if isinstance(vehicle['id'], str):
                vehicle['id'] = int(vehicle['id'])

            if vehicle['id'] == ud.blackboard.message['how']['vehicle_id']:
                for site in sites:
                    if isinstance(vehicle['site'], str):
                        vehicle['site'] = int(vehicle['site'])

                    if isinstance(site['id'], str):
                        site['id'] = int(site['id'])

                    if vehicle['site'] == site['id']:
                        ud.blackboard.message['how'].update({'site': site['id']})
                        ud.blackboard.message['how'].update({'vehicle_mid': vehicle['mid']})

        t = ud.blackboard.message['who']
        ud.blackboard.message['who'] = [t, 'springgos_sejong_2']
        rospy.logdebug(json.dumps(ud.blackboard.message, indent=4, sort_keys=True))

        #client.sendMessage(json.dumps(data))
        #rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))
        #print(json.dumps(ud.blackboard.message, indent=4, sort_keys=True))

        return 'succeeded'

class get_msg_until_10sec(smach.State):
    def __init__(self, server, queue):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.server = server
        self.queue = queue
        self.timeout = 5
    def execute(self, ud):
        start_time = time.time()
        while True:
            if time.time() - start_time > self.timeout:
                return 'timeout'
            try:
                # With False, the queue does not block the program.
                # It raises Queue.Empty if empty.
                client, kind, message = self.queue.get(False)
            except Queue.Empty:
                kind = None

            if kind is not None:
                # parsing...

                self.queue.task_done()
                break
            time.sleep(0.1)


        #data = None
        #with open('/ws/src/app_to_django/vehicles.json') as json_file:
        #    data = json.load(json_file)
        #    print(type(data))

        #client.sendMessage(json.dumps(data))
        #rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))
        #print(json.dumps(ud.blackboard.message, indent=4, sort_keys=True))

        return 'succeeded'


class check_10hour(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

        self.timeout = 36000
        self.start_time = time.time()
    def execute(self, ud):
        if time.time() - self.start_time > self.timeout:
            return 'timeout'
        return 'succeeded'


class KeyPress(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded',
                                             'preempted',
                                             'aborted'
                                             ],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
    def execute(self, ud):
        try:
            used_result = py_trees.console.read_single_keypress()
            if used_result == '1':

                print(os.getcwd())
                print(os.path.realpath(__file__))
                print(os.path.dirname(os.path.realpath(__file__)))

                rospy.loginfo("The Answer was 1!")
                url = 'http://httpbin.org/post'
                files = {'bagging_file': open(os.path.dirname(os.path.realpath(__file__))+'/tmp.bag', 'rb')}
                r = requests.post(url, files=files)
                print(r.text)
            elif used_result == '2':
                rospy.loginfo("The Answer was 2!")
            elif used_result == '3':
                rospy.loginfo("The Answer was 3!")
            elif used_result == '4':
                rospy.loginfo("The Answer was 4!")
        except KeyboardInterrupt:
            rospy.logerr("Interrupted by user")
            return 'aborted'
        return 'succeeded'


class UploadFiles(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded',
                                             'preempted',
                                             'aborted'
                                             ],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.diagnostic_updater = diagnostic_updater.Updater()
        self.diagnostic_updater.setHardwareID("upload")
        self.diagnostic_updater.add("upload", self.diagnosticCallback)


    def execute(self, ud):
        timer = rospy.Timer(rospy.Duration(1), self.diagnosticTimerCallback)

        try:
            url = 'http://211.233.76.241:5100/api/v1/upload/files'
            url = 'http://httpbin.org/post'
            path = os.path.dirname(os.path.realpath(__file__)) + '/tmp.bag'
            if os.path.isfile(path):
                file_size = self.file_size(path)
                files = {'bagging_file': open(path, 'rb')}
                start_time = time.time()
                r = requests.post(url, files=files)
                print(r.text)
                elapsed_time = time.time() - start_time
                print('elapse/data', time.strftime("%H:%M:%S", time.gmtime(elapsed_time))+'/'+file_size)

        except KeyboardInterrupt:
            rospy.logerr("Interrupted by user")
            timer.shutdown()
            return 'aborted'

        timer.shutdown()
        return 'succeeded'


    def convert_bytes(self, num):
        """
        this function will convert bytes to MB.... GB... etc
        """
        for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
            if num < 1024.0:
                return "%3.1f %s" % (num, x)
            num /= 1024.0

    def file_size(self, file_path):
        """
        this function will return the file size
        """
        if os.path.isfile(file_path):
            file_info = os.stat(file_path)
            return self.convert_bytes(file_info.st_size)

    def diagnosticTimerCallback(self, event):
        self.diagnostic_updater.update()

    def diagnosticCallback(self, stat):
        # always OK
        stat.summary(DiagnosticStatus.OK, "OK")
        return stat

class Rosbag(smach.State):
    def __init__(self, config):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.config = config
        self.duration = config.duration
        self.diagnostic_updater = diagnostic_updater.Updater()
        self.diagnostic_updater.setHardwareID("rosbag")
        self.diagnostic_updater.add("rosbag", self.diagnosticCallback)

    def execute(self, ud):
        package = 'rosbag'
        executable = 'record'
        timer = rospy.Timer(rospy.Duration(1), self.diagnosticTimerCallback)
        try:
            file = os.path.dirname(os.path.realpath(__file__))+'/tmp.bag'
            args = "--duration={0}s --bz2 -a -b 0 -O {1}".format(str(self.duration), file)
            node = roslaunch.core.Node(package, executable, args=args, name='bag_test', output='screen')
            launch = roslaunch.scriptapi.ROSLaunch()
            launch.start()
            process = launch.launch(node)
        except roslaunch.core.RLException:
            timer.shutdown()
            return 'aborted'

        try:
            while process.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("Interrupted by user, shutting down...")

        timer.shutdown()
        return 'succeeded'

    def diagnosticTimerCallback(self, event):
        self.diagnostic_updater.update()

    def diagnosticCallback(self, stat):
        # always OK
        stat.summary(DiagnosticStatus.OK, "OK")
        return stat

class preempted_timeout(smach.State):
    def __init__(self, timeout):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.timeout = timeout
        rospy.loginfo('timeout is {}'.format(self.timeout))

    def execute(self, ud):
        start_time = time.time()
        while True:
            if self.preempt_requested():
                self.service_preempt()
                return 'preempted'
            time.sleep(0.2)
            if time.time() - start_time > self.timeout:
                break
        return 'succeeded'


class publising(smach.State):
    def __init__(self, config):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        # assign config
        # value: timeout(60), topic('/diagnostics'), buffer(2)
        self.config = config
        self.timeout = config.timeout
        self.diagnostic = None
        self.pub = rospy.Publisher(self.config.topic, diagnostic_msgs.msg.DiagnosticArray, queue_size=self.config.buffer)

    def execute(self, ud):
        start_time = time.time()
        # simulated
        diag = diagnostic_msgs.msg.DiagnosticArray()
        diag.header.stamp = rospy.Time.now()
        # battery info
        stat = diagnostic_msgs.msg.DiagnosticStatus()

        stat.name = "Battery"
        stat.level = diagnostic_msgs.msg.DiagnosticStatus.OK
        stat.message = "OK"
        stat.values.append(diagnostic_msgs.msg.KeyValue("Status", '%s (%s)' % ('1', '2')))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Time to Empty/Full (minutes)", str(2)))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Voltage (V)", str(12)))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Current (A)", str(1)))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Charge (Ah)", str(2)))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Charge (%)", str(1)))
        stat.values.append(diagnostic_msgs.msg.KeyValue("Capacity (Ah)", str(2)))
        diag.status.append(stat)
        self.pub.publish(diag)

        try:
            while True:
                if self.preempt_requested():
                    self.service_preempt()
                    return 'preempted'
                time.sleep(0.2)
                if time.time() - start_time > self.timeout:
                    break
        except KeyboardInterrupt:
            print("Interrupted by user, shutting down...")
            ud.blackboard.pid.send_signal(signal.SIGINT)
            return 'aborted'
        return 'succeeded'


class cctv(smach.State):
    def __init__(self, config):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        # assign config
        # value: id(0), bitrate(4000000), host(192.168.0.221), port(5000)
        self.config = config
        self.gst_str = ("gst-launch-1.0 "
                        "nvcamerasrc sensor_id={0} fpsRange=\"30 30\" intent=3 ! "
                        "nvvidconv flip-method=0 ! "
                        "video/x-raw(memory:NVMM) ! "
                        "omxh264enc control-rate=2 bitrate={1} ! "
                        "video/x-h264, stream-format=(string)byte-stream ! "
                        "h264parse ! "
                        "rtph264pay mtu=1400 ! "
                        "udpsink host={2} port={3} sync=false async=false ").format(self.config.id, self.config.bitrate,
                                                                                    self.config.host, self.config.port)

    def execute(self, ud):
        self.start()

        # Ref https://stackoverflow.com/questions/7681715/whats-the-difference-between-subprocess-popen-and-call-how-can-i-use-them
        ud.blackboard.pid = subprocess.Popen(self.gst_str.split())
        time.sleep(2)

        self.stop()
        return 'succeeded'

    def start(self):
        pass

    def stop(self):
        pass


@smach.cb_interface(outcomes=['succeeded',
                              'preempted',
                              'aborted'
                              ],
                    input_keys=['blackboard'],
                    output_keys=['blackboard'])
def trigger(ud):
    # Ref: http://wiki.ros.org/rospy/Overview/Services
    rospy.wait_for_service('/router/start')
    fn_empty = rospy.ServiceProxy('/router/start', std_srvs.srv.Empty)
    try:
        fn_empty()
        rospy.loginfo('called /router/start subscriber')
    except rospy.ServiceException as exc:
        print("Service did not process request: " + str(exc))

    return 'succeeded'
