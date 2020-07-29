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
# added 2020.06.15
from requests.auth import HTTPBasicAuth
import kafka
from geopy.distance import great_circle

from datetime import datetime

# added 2020.6.27 for dust api
import xmltodict

# eta
from .ETA import Sites_Estiamtetime, ETA_sta2sta

# InsecureRequestWarning: Unverified HTTPS request is being made to host '115.93.143.2'.
# Adding certificate verification is strongly advised.
# See: https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


'''
app_to_django    | [DEBUG] [1592372886.770086]: {
app_to_django    |     "how": {
app_to_django    |         "accumulated_passenger": 17,
app_to_django    |         "current_passenger": 1,
app_to_django    |         "site": 2,
app_to_django    |         "type": "PASSENGER",
app_to_django    |         "vehicle_id": 6,
app_to_django    |         "vehicle_mid": "SCN999"
app_to_django    |     },
app_to_django    |     "version": 1,
app_to_django    |     "what": "EVENT",
app_to_django    |     "when": 1592372883.060738,
app_to_django    |     "where": "sejong_datahub",
app_to_django    |     "who": [
app_to_django    |         "android app",
app_to_django    |         "springgos_sejong_2"
app_to_django    |     ]
app_to_django    | }

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
    tasio -> server
    when: timestamp
    where: site pk
    who: [tasio]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        command: call
    }
    safe -> server
    who: [safe]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        command: go
    }
    safe -> server
    who: [safe]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        command: arrived
    }
    server -> safe
    who: [tasio, server]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        vehicle_mid:
        site:
        command: call
    }
    server -> tasio
    who: [safe, server]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        vehicle_mid:
        site:
        command: go
    }
    server -> web[x]
    who: [safe, server]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        vehicle_mid:
        site:
        command: go
    }
    server -> tasio
    who: [safe, server]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        vehicle_mid:
        site:
        command: arrived
    }
    server -> web[x]
    who: [safe, server]
    what: request
    how: {
        type: ondemand
        vehicle_id:
        vehicle_mid:
        site:
        command: arrived
    }

    server -> connected client
    who: [connected client, server]
    what: request
    how: {
        type: identity
        address: 211.134.131.2
    }
    connected client -> server
    who: [connected client]
    what: resp
    how: {
        type: identity
        identity: tasio_3949
    }
}
'''


def init_blackboard():
    blackboard = py_trees.blackboard.Blackboard()
    blackboard.pid = None
    blackboard.client = None
    blackboard.message = {
        "version": 1,
        "when": time.time(),
        "where": 'sejong_datahub',
        "who": 'android app',
        "what": 'EVENT',  # REQ, RESP ,EVET, ERROR
        "how": {
            "type": 'PASSENGER',  # 'POWER', 'DOOR'
            "vehicle_id": 6,
            "current_passenger": 1,
            "accumulated_passenger": 17
        }
    }
    blackboard.weather = {}
    blackboard.forecast = {}
    blackboard.dust = {}
    return blackboard


class make_eta_from_kafka_until_10min(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

        self.broker = '175.203.98.23:9092'
        self.topic = 'sgs-kiosk-vehicle'  # sim-vehicle
        self.group = 'sgs-nifi-consumer005'
        self.consumer = kafka.KafkaConsumer(self.topic,
                                            bootstrap_servers=[self.broker], group_id=self.group,
                                            enable_auto_commit=True, consumer_timeout_ms=600000  # 10min
                                            )

    def execute(self, ud):
        stations = None
        with open('/ws/src/app_to_django/stations.json') as json_file:
            stations = json.load(json_file)

        for msg in self.consumer:
            try:
                if not len(msg) or not len(msg.value):
                    continue
                packet = json.loads(msg.value)  # string to dictionary
                if not isinstance(packet, dict):
                    continue

                if 'type' in packet:
                    if packet['type'] != 'gnss':  # only get gnss pacet
                        continue

                lata = 0.0
                lona = 0.0
                latb = 0.0
                lonb = 0.0

                if 'message' in packet:
                    # test
                    # if 'vhcle_id' in packet['message']:
                    #    if packet['message']['vhcle_id'] != 'SCN001':
                    #        continue

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
                            # rospy.loginfo("site %d, station %s, %fm", station['site'], station['mid'], great_circle(a, b).m)

                # rospy.logdebug(json.dumps(packet, indent=4, sort_keys=True))
                return 'succeeded'
            except UnicodeError as e:
                rospy.logerr('UnicodeError {}'.format(e))
            except TypeError as e:
                rospy.logerr('TypeError {}'.format(e))
            except KeyError as e:
                rospy.logerr('KeyError {}'.format(e))
            except SyntaxError as e:
                rospy.logerr('SyntaxError {}'.format(e))
            except NameError as e:
                rospy.logerr('NameError {}'.format(e))

        return 'timeout'


class get_vehicle_site_from_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        try:
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            url = 'https://test.aspringcloud.com/api/sites'
            sites = requests.request(
                method='get',
                url=url,
                auth=auth_ones,
                verify=None,
                headers={'Content-type': 'application/json'}
            )
            rospy.loginfo('{}, {}'.format(url, sites.status_code))
            url = 'https://test.aspringcloud.com/api/vehicles'
            vehicles = requests.request(
                method='get',
                url=url,
                auth=auth_ones,
                verify=None,
                headers={'Content-type': 'application/json'}
            )
            rospy.loginfo('{}, {}'.format(url, vehicles.status_code))

            # [chang-gi] 20.07.29 - 안전 요원의 도착 예정시간 취득을 위한 추가.
            url = 'https://test.aspringcloud.com/api/stations'
            stations = requests.request(
                method='get',
                url=url,
                auth=auth_ones,
                verify=None,
                headers={'Content-type': 'application/json'}
            )
            rospy.loginfo('{}, {}'.format(url, stations.status_code))

            with open('/ws/src/app_to_django/vehicles.json', 'w') as json_file:
                json.dump(vehicles.json(), json_file)

            
            with open('/ws/src/app_to_django/sites.json', 'w') as json_file:
                json.dump(sites.json(), json_file)

            with open('/ws/src/app_to_django/stations.json', 'w') as json_file:
                json.dump(stations.json(), json_file)

            
        except requests.exceptions.RequestException as e:
            rospy.logerr('requests {}'.format(e))
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
            url = 'https://test.aspringcloud.com/api/stations'
            stations = requests.request(
                method='get',
                url=url,
                auth=auth_ones,
                verify=None,
                headers={'Content-type': 'application/json'}
            )
            rospy.loginfo('{}, {}'.format(url, stations.status_code))
            with open('/ws/src/app_to_django/stations.json', 'w') as json_file:
                json.dump(stations.json(), json_file)
        except requests.exceptions.RequestException as e:
            rospy.logerr('requests {}'.format(e))
            return 'aborted'
        return 'succeeded'


class ping_to_clients(smach.State):
    def __init__(self, server):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.server = server
        self.timeout = 10
        self.start_time = time.time()

    def execute(self, ud):
        if time.time() - self.start_time > self.timeout:
            for client in self.server.get_all_connections():
                
                data = {'version': 1,
                        'when': time.time(),
                        'where': 'sejong_datahub',
                        'what': 'PING',
                        'who': "springgos_sejong_1",
                        'how': {'ipaddr': client.address}
                        }
                client.sendMessage(json.dumps(data))
                # rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))
                rospy.logdebug('{} PING'.format(client))
            self.start_time = time.time()
        return 'succeeded'


class post_event_to_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        how = ud.blackboard.message['how']
        rospy.loginfo('{}, {}'.format(how, ud.blackboard.message))
        data = {}
        pk = None
        if 'vehicle_id' in how:
            pk = how['vehicle_id']

        if 'type' in how:
            if how['type'] == 'passenger':
                data['passenger'] = how['current_passenger']
            if how['type'] == 'power':
                pass
            if how['type'] == 'parking':
                data['isparked'] = how['value']
            if how['type'] == 'drive':
                if how['value'] == 'auto':
                    data['drive'] = True
                else:
                    data['drive'] = False
            if how['type'] == 'door':
                data['door'] = how['value']
            if how['type'] == 'message':
                pass
            if how['type'] == 'station':
                data['passed_station'] = how['value']

        if not data:
            rospy.logerr('empty data to post')
            return 'succeeded'

        auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
        url = 'https://test.aspringcloud.com/api/vehicles/{}/'.format(pk)
        r = requests.request(
            method='patch',
            url=url,
            data=json.dumps(data),
            auth=auth_ones,
            verify=None,
            headers={'Content-type': 'application/json'}
        )
        if r is not None:
            if r.status_code != 200:
                rospy.logerr('patch/' + r.reason)
            else:
                rospy.loginfo('{}, {}'.format(url, r.status_code))

        url = 'http://115.93.143.2:9103/api/vehicles/{}/'.format(pk)
        r = requests.request(
            method='patch',
            url=url,
            data=json.dumps(data),
            auth=auth_ones,
            verify=None,
            headers={'Content-type': 'application/json'}
        )
        if r is not None:
            if r.status_code != 200:
                rospy.logerr('103 patch/' + r.reason)
            else:
                rospy.loginfo('{}, {}'.format(url, r.status_code))
        rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))

        return 'succeeded'


class estiamte_eta_and_post(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.gstations = {1:[9,10,11,12,13, 18, 19], 2:[1, 2, 3, 4]}
        self.gsite_id = [1, 2]
    def execute(self, ud):
        data = {}
        try:
            #대구도 작동하게 하기 위한 변경
            for gsiteindex in self.gsite_id:
                for station in self.gstations[gsiteindex]:
                    veta = Sites_Estiamtetime(gsiteindex, station)
                    # for v_id, eta in veta.items():
                    #     print(station, v_id, eta)
                    data['eta'] = []  # veta가 list로 되어야 하는거아닌가?
                    data['eta'].append(json.dumps(veta))

                    # Station 2 Station 서버 구성.
                    ceta = ETA_sta2sta(station, gsiteindex)
                    data['stat2sta'] = []  
                    data['stat2sta'].append(json.dumps(ceta))

                    auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
                    url = 'https://test.aspringcloud.com/api/stations/{}/'.format(station)
                    r = requests.request(
                        method='patch',
                        url=url,
                        data=json.dumps(data),
                        auth=auth_ones,
                        verify=False,
                        headers={'Content-type': 'application/json'}
                    )
                    if r is not None:
                        if r.status_code != 200:
                            rospy.logerr('patch/' + r.reason)
                        else:
                            rospy.loginfo('{}, {}'.format(url, r.status_code))

                    url = 'http://115.93.143.2:9103/api/stations/{}/'.format(station)
                    r = requests.request(
                        method='patch',
                        url=url,
                        data=json.dumps(data),
                        auth=auth_ones,
                        verify=False,
                        headers={'Content-type': 'application/json'}
                    )
                    if r is not None:
                        if r.status_code != 200:
                            rospy.logerr('103 patch/' + r.reason)
                        else:
                            rospy.loginfo('{}, {}'.format(url, r.status_code))
                    rospy.loginfo(json.dumps(data, indent=4, sort_keys=True))

        except requests.exceptions.RequestException as e:  # Max retries exceeded with
            rospy.logerr('requests {}'.format(e))
            return 'succeeded'  # retry
        return 'succeeded'

        
class post_eta_to_django_by_1sec(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.timeout = 2
        self.start_time = time.time()

    def execute(self, ud):
        if time.time() - self.start_time > self.timeout:
            pk = 1
            data = {}
            station_01 = {
                'id': 1,
                'mid': 'STA001',
                'eta': 13,  # minute
                'distance': 130,  # meter
                'passed_station': False
            }
            station_02 = {
                'id': 2,
                'mid': 'STA002',
                'eta': 23,  # minute
                'distance': 230,  # meter
                'passed_station': False
            }
            station_03 = {
                'id': 3,
                'mid': 'STA003',
                'eta': 33,  # minute
                'distance': 330,  # meter
                'passed_station': False
            }
            station_04 = {
                'id': 4,
                'mid': 'STA004',
                'eta': 43,  # minute
                'distance': 140,  # meter
                'passed_station': True
            }
            data['eta'] = []
            data['eta'].append(json.dumps(station_01))
            data['eta'].append(json.dumps(station_02))
            data['eta'].append(json.dumps(station_03))
            data['eta'].append(json.dumps(station_04))

            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            url = 'https://test.aspringcloud.com/api/vehicles/{}/'.format(pk)
            r = requests.request(
                method='patch',
                url=url,
                data=json.dumps(data),
                auth=auth_ones,
                verify=False,
                headers={'Content-type': 'application/json'}
            )
            if r is not None:
                if r.status_code != 200:
                    rospy.logerr('patch/' + r.reason)
                else:
                    rospy.loginfo('{}, {}'.format(url, r.status_code))
            rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))
            self.start_time = time.time()
        return 'succeeded'


class dummy(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        # start_time = time.time()

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
        return 'succeeded'


class get_msg_until_sec(smach.State):
    def __init__(self, server, queue, timeout):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.server = server
        self.queue = queue
        self.timeout = timeout

    def execute(self, ud):
        start_time = time.time()
        while True:
            if time.time() - start_time > self.timeout:
                return 'timeout'
            try:
                # With False, the queue does not block the program.
                # It raises Queue.Empty if empty.
                ud.blackboard.client, kind, ud.blackboard.message = self.queue.get(False)
                ud.blackboard.message = eval(ud.blackboard.message)  # unicode to dictionary
                rospy.logdebug("queue[after]=>"+json.dumps(ud.blackboard.message, indent=4, sort_keys=True)) 
            except Queue.Empty:
                kind = None
            except KeyError as e:
                kind = None
                rospy.logerr('KeyError {}'.format(e))
            except SyntaxError as e:
                kind = None
                rospy.logerr('SyntaxError {}'.format(e))
            except NameError as e:
                kind = None
                rospy.logerr('NameError {}'.format(e))

            if kind is not None:
                # parsing...
                '''{
                "how": {
                    "accumulated_passenger": 17,
                    "current_passenger": 1,
                    "site": 2,
                    "type": "PASSENGER",
                    "vehicle_id": 6,
                    "vehicle_mid": "SCN999"
                    },
                "version": 1,
                "what": "EVENT",
                "when": 1592372883.060738,
                "where": "sejong_datahub",
                "who": ["android app", "springgos_sejong_1"]
                }'''
                self.queue.task_done()
                break
            time.sleep(0.2)

        vehicles = None
        sites = None
        stations = None

        with open('/ws/src/app_to_django/vehicles.json') as json_file:
            vehicles = json.load(json_file)
        with open('/ws/src/app_to_django/sites.json') as json_file:
            sites = json.load(json_file)

        # [chang-gi] 20.07.29 - 안전 요원의 도착 예정시간 취득을 위한 추가.
        with open('/ws/src/app_to_django/stations.json') as json_file:
            stations = json.load(json_file)

        # 7월 28일 - Socket 문제 해결을 위한 변경.
        #sites = sites['results']

        if 'what' in ud.blackboard.message:
            if ud.blackboard.message['what'] != 'REQ' and ud.blackboard.message['what'] != 'EVENT':
                rospy.loginfo('REQ or EVENT or PING {}'.format(json.dumps(ud.blackboard.message, indent=4, sort_keys=True)))
                return 'timeout'

        is_validated = False
        for vehicle in vehicles:
            if 'how' in ud.blackboard.message:
                if 'vehicle_id' in ud.blackboard.message['how']:
                    if isinstance(ud.blackboard.message['how']['vehicle_id'], str):
                        ud.blackboard.message['how']['vehicle_id'] = int(ud.blackboard.message['how']['vehicle_id'])
                    if isinstance(vehicle['id'], str):
                        vehicle['id'] = int(vehicle['id'])
                        
                    # rospy.logerr("vehicle['site'] == site['id']{}/{}".format(vehicle['id'], ud.blackboard.message['how']['vehicle_id']))
                    if vehicle['id'] == ud.blackboard.message['how']['vehicle_id']:
                        for site in sites:
                            if isinstance(vehicle['site'], str):
                                vehicle['site'] = int(vehicle['site'])

                            if isinstance(site['id'], str):
                                site['id'] = int(site['id'])

                            if vehicle['site'] == site['id']:
                                rospy.logerr("vehicle['site'] == site['id']")
                                ud.blackboard.message['how'].update({'site_id': site['id']})
                                ud.blackboard.message['how'].update({'vehicle_mid': vehicle['mid']})
                                break
                        ud.blackboard.message['when'] = time.time()
                        ud.blackboard.message['who'] = 'springgos_sejong_1'
                        ud.blackboard.message['where'] = 'sejong_datahub'
                        # rospy.logdebug(json.dumps(ud.blackboard.message, indent=4, sort_keys=True))
                        is_validated = True
                        break

        if is_validated:
            for client in self.server.get_all_connections():
                if ud.blackboard.client == client:
                    ud.blackboard.message['what'] = 'RESP'
                    client.sendMessage(json.dumps(ud.blackboard.message))
                    # rospy.logdebug("what='RESP'==>{}".format(json.dumps(ud.blackboard.message, indent=4, sort_keys=True)))
                else:
                    ud.blackboard.message['what'] = 'EVENT'

                    is_ondemand = False
                    is_message = False
                    is_function_call = False
                    is_function_start = False
                    is_function_complete = False
                    is_function_cancelcall = False
                    if 'type' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['type'] == 'ondemand':
                            is_ondemand = True

                    if 'type' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['type'] == 'message':
                            is_message = True

                    if 'function' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['function'] == 'go':
                            is_function_start = True
                    
                    if 'function' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['function'] == 'call':
                            is_function_call = True
                    
                    if 'function' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['function'] == 'arrived':
                            is_function_complete = True

                    if 'function' in ud.blackboard.message['how']:
                        if ud.blackboard.message['how']['function'] == 'cancel_call':
                            is_function_cancelcall = True

                    #테스트용 코드 작성
                    rospy.loginfo('is_ondemand>>'+str(is_ondemand))
                    rospy.loginfo('is_message>>'+str(is_message))
                    rospy.loginfo('is_function_call>>'+str(is_function_call))
                    rospy.loginfo('is_function_start>>'+str(is_function_start))
                    rospy.loginfo('is_function_complete>>'+str(is_function_complete))
                    rospy.loginfo('is_function_cancelcall>>'+str(is_function_cancelcall))
                    
                    if is_ondemand and is_function_start:
                        '''
                        예상도착시간, 예상이동시간
                        '''
                        rospy.loginfo('is_function_start')
                        ud.blackboard.message['how'].update({'eta': 1})
                        client.sendMessage(json.dumps(ud.blackboard.message))

                    if is_ondemand and is_function_call:
                        '''
                        새로운 필드 추가
                        '''
                        # [chang-gi] 20.07.29 - 안전 요원의 도착 예정시간 취득을 위한 추가.
                        # current_station_eta : 현재 정류장까지 오는데 걸리는 시간
                        # target_station_eta : 목적지 정류장까지 오는데 걸리는 시간.

                        for station_index in stations:
                            # current_station_eta 구성
                            current_station_id = str(ud.blackboard.message['how']['current_station_id'])

                            if isinstance(station_index['id'], int):
                                station_index['id'] = str(station_index['id'])

                            # Stations의 id가 패킷의 출발 station의 id와 같을 경우. ==> 해당 site의 모든 차량에 대한 ETA 정보 송신
                            if station_index['id'] == current_station_id:
                                ud.blackboard.message['how'].update({'current_station_eta': station_index['eta']})

                                # target_station_eta 구성
                                stat2sta = eval(station_index['stat2sta'][0])
                                target_station_id = str(ud.blackboard.message['how']['target_station_id'])

                                ud.blackboard.message['how'].update({'target_station_eta': stat2sta[current_station_id][target_station_id]})
                                                        
                        # tasio에서는 어떤 차량인지 모른다.
                        ud.blackboard.message['how'].update({'vehicle_id': 4})
                        client.sendMessage(json.dumps(ud.blackboard.message))

                    if is_ondemand and is_function_cancelcall:
                        '''
                        add new field.
                        '''
                        rospy.loginfo('is_function_cancelcall')
                        ud.blackboard.message['how'].update({'vehicle_id': 4})
                        client.sendMessage(json.dumps(ud.blackboard.message))

                    if is_ondemand and is_function_complete:
                        '''
                        새로운 필드 추가
                        '''
                        rospy.loginfo('is_function_complete')
                        client.sendMessage(json.dumps(ud.blackboard.message))

                    if is_message:
                        rospy.loginfo('is_message')
                        # print(type(ud.blackboard.message["how"]["value"]))
                        # ud.blackboard.message["how"]["value"] = "안녕하세요"
                        client.sendMessage(json.dumps(ud.blackboard.message))

                    # else: ondemand 이외에는 처리 하지 않는다.
                    #     client.sendMessage(json.dumps(ud.blackboard.message))

                    rospy.logdebug("==> "+json.dumps(ud.blackboard.message, indent=4, sort_keys=True))
            return 'succeeded'

        return 'timeout'


class check_10hour(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted', 'timeout'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

        self.timeout = 36000
        self.start_time = time.time()

    def execute(self, ud):
        if time.time() - self.start_time > self.timeout:
            self.start_time = time.time()
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
                files = {'bagging_file': open(os.path.dirname(os.path.realpath(__file__)) + '/tmp.bag', 'rb')}
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
                print('elapse/data', time.strftime("%H:%M:%S", time.gmtime(elapsed_time)) + '/' + file_size)

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
            file = os.path.dirname(os.path.realpath(__file__)) + '/tmp.bag'
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


class get_weather_from_opensite_and_post(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.weather_api_keys = '478828da0e79a958cc52abb2d47fad95'

    def execute(self, ud):
        try:
            garages = None
            with open('/ws/src/app_to_django/garages.json') as json_file:
                garages = json.load(json_file)
            garages = garages['results']
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            for garage in garages:
                lat = float(garage['lat'])
                lon = float(garage['lon'])

                current, houly = self.daily_weather(lat, lon)
                # rospy.loginfo('{},{}'.format(current,houly))

                data = {}
                data['current_weather'] = json.dumps(current)
                data['weather_forecast'] = json.dumps(houly)

                pk = garage['site']
                url = 'https://test.aspringcloud.com/api/sites/{}/'.format(pk)
                # print(url)
                r = requests.request(
                    method='patch',
                    url=url,
                    data=json.dumps(data),
                    auth=auth_ones,
                    verify=False,
                    headers={'Content-type': 'application/json'}
                )
                if r is not None:
                    if r.status_code != 200:
                        rospy.logerr('patch/' + r.reason)
                    else:
                        rospy.loginfo('{}, {}'.format(url, r.status_code))

                url = 'http://115.93.143.2:9103/api/sites/{}/'.format(pk)
                r = requests.request(
                    method='patch',
                    url=url,
                    data=json.dumps(data),
                    auth=auth_ones,
                    verify=False,
                    headers={'Content-type': 'application/json'}
                )
                if r is not None:
                    if r.status_code != 200:
                        rospy.logerr('103 patch/' + r.reason)
                    else:
                        rospy.loginfo('{}, {}'.format(url, r.status_code))
                rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))

        except TypeError as e:
            rospy.logerr('TypeError {}'.format(e))
        except KeyError as e:
            rospy.logerr('KeyError {}'.format(e))
        except SyntaxError as e:
            rospy.logerr('SyntaxError {}'.format(e))
        except NameError as e:
            rospy.logerr('NameError {}'.format(e))

        return 'succeeded'

    def categorization_WeatherState(self, pngname):
        # 해당 정보는 아래의 링크를 따른다.
        # https://openweathermap.org/weather-conditions
        if pngname[:2] in ('01', '02'):
            return 'good'
        elif pngname[:2] in ('03', '04', '50'):
            return 'cloudy'
        elif pngname[:2] in ('09', '10', '11'):
            return 'rainy'
        else:
            return 'snow'

    def daily_weather(self, lat, lon):
        apiAddr = 'https://api.openweathermap.org/data/2.5/onecall'
        params = {'lat': lat, 'lon': lon, 'lang': 'kr', 'units': 'metric', 'appid': self.weather_api_keys, "exclude": 'daily'}
        res = requests.get(apiAddr, params=params)
        WeatherData = res.json()

        """
        lat 위치의 지리적 좌표 (위도)
        lon 위치의 지리적 좌표 (경도)
        timezone 요청한 위치의 시간대 이름
        timezone_offset UTC에서 초 단위로 이동

        current : 데이터 포인트 dt는 현재 시간이 아닌 요청 된 시간을 나타냅니다.
            current.dt 요청 된 시간, 유닉스, UTC
            current.sunrise 일출 시간, 유닉스, UTC
            current.sunset 일몰 시간, 유닉스, UTC
            current.temp온도. 단위 기본값 : 켈빈, 미터법 : 섭씨, 임페리얼 : 화씨. 단위 형식을 변경하는 방법
            current.feels_like온도. 이 온도 매개 변수는 날씨에 대한 인간의 인식을 설명합니다. 단위 기본값 : 켈빈, 미터법 : 섭씨, 임페리얼 : 화씨.
            current.pressure 해수면의 대기압, hPa
            current.humidity 습도, %
            current.dew_point물방울이 응축되기 시작하는 대기 온도 (압력 및 습도에 따라 변함)는 이슬이 형성 될 수 있습니다. 단위 기본값 : 켈빈, 미터법 : 섭씨, 임페리얼 : 화씨.
            current.clouds 흐림, %
            current.uvi 정오 UV 인덱스
            current.visibility 평균 가시성, 미터
            current.wind_speed바람 속도. 단위 기본값 : 미터 / 초, 미터법 : 미터 / 초, 임페리얼 : 마일 / 시간. 단위 형식을 변경하는 방법
            current.wind_gust바람 돌풍. 단위 기본값 : 미터 / 초, 미터법 : 미터 / 초, 임페리얼 : 마일 / 시간. 단위 형식을 변경하는 방법
            current.wind_deg 풍향,도 (기상)
            current.rain 강수량, mm
            current.snow 제 설량, mm
            current.weather (자세한 정보 기상 조건 코드)
            current.weather.id 기상 조건 ID
                current.weather.main 날씨 매개 변수 그룹 (비, 눈, 극한 등)
                current.weather.description그룹 내 날씨 조건 ( 날씨 조건 전체 목록 ) 당신의 언어로 결과를 얻으십시오
                current.weather.icon날씨 아이콘 ID 아이콘을 얻는 방법"""

        # nowHour = datetime.now().strftime('%H')
        needTime = [9, 12, 15, 18]
        HoulyData = {}
        for HoulyIndex in WeatherData['hourly']:
            s = HoulyIndex['dt']
            time = int(datetime.utcfromtimestamp(s).strftime('%H'))
            now = int(datetime.now().strftime('%H'))
            if int(time) in needTime:
                HoulyData.setdefault(int(datetime.utcfromtimestamp(s).strftime('%H')),)
                # 날씨 구분
                HoulyData[time] = {'temp': HoulyIndex['temp'], 'weather': self.categorization_WeatherState(HoulyIndex['weather'][0]['icon'])}
            if now == time:
                # print(HoulyIndex['weather'][0]['icon'])
                CurrentWeatherData = {'temp': HoulyIndex['temp'], 'weather': self.categorization_WeatherState(HoulyIndex['weather'][0]['icon'])}

        return CurrentWeatherData, HoulyData


class post_weather_to_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        return 'succeeded'


class get_site_from_django(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])

    def execute(self, ud):
        try:
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            url = 'https://test.aspringcloud.com/api/garages'
            garages = requests.request(
                method='get',
                url=url,
                auth=auth_ones,
                verify=None,
                headers={'Content-type': 'application/json'}
            )
            rospy.loginfo('{}, {}'.format(url, garages.status_code))
            with open('/ws/src/app_to_django/garages.json', 'w') as json_file:
                json.dump(garages.json(), json_file)

        except requests.exceptions.RequestException as e:
            rospy.logerr('requests {}'.format(e))
            return 'aborted'

        return 'succeeded'


class get_dust_from_opensite_and_post(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.dust_api_keys = 'zHKzBSmpIIz6sd3aUeDAW5Ee7BoMdjVN%2FF9yTZFDyHeYzL6sKz44TA3sypR0Sg%2BPbqtGX5lRNE0Yj3MvI6aJ0w%3D%3D'
        # 카카오 Developers key [ 1일 1만건 가능]
        # 관련 API 링크
        # https://developers.kakao.com/docs/latest/ko/local/dev-guide
        self.KaKaoRestAPIKey = 'ea2dfc54f13d1eeaeca07fd6fcf11c53'
        self.Host = 'https://dapi.kakao.com'
        self.APIAddr = '/v2/local/geo/coord2address.json?input_coord=WGS84'

    def execute(self, ud):
        try:
            garages = None
            with open('/ws/src/app_to_django/garages.json') as json_file:
                garages = json.load(json_file)
            garages = garages['results']
            auth_ones = HTTPBasicAuth('bcc@abc.com', 'chlqudcjf')
            for garage in garages:
                lat = float(garage['lat'])
                lon = float(garage['lon'])
                ret = self.DustNOzoneInfo(lon, lat)
                if ret is False:
                    rospy.logerr('get error from DustNOzoneInfo')
                    continue

                # current, houly = self.daily_weather(lat,lon)
                # rospy.loginfo('{},{}'.format(current,houly))
                # print(type(ret))
                data = {}
                data['air_quality'] = json.dumps(ret)

                pk = garage['site']
                url = 'https://test.aspringcloud.com/api/sites/{}/'.format(pk)
                # print(url)
                r = requests.request(
                    method='patch',
                    url=url,
                    data=json.dumps(data),
                    auth=auth_ones,
                    verify=False,
                    headers={'Content-type': 'application/json'}
                )
                if r is not None:
                    if r.status_code != 200:
                        rospy.logerr('patch/' + r.reason)
                    else:
                        rospy.loginfo('{}, {}'.format(url, r.status_code))

                url = 'http://115.93.143.2:9103/api/sites/{}/'.format(pk)
                r = requests.request(
                    method='patch',
                    url=url,
                    data=json.dumps(data),
                    auth=auth_ones,
                    verify=False,
                    headers={'Content-type': 'application/json'}
                )
                if r is not None:
                    if r.status_code != 200:
                        rospy.logerr('103 patch/' + r.reason)
                    else:
                        rospy.loginfo('{}, {}'.format(url, r.status_code))
                rospy.logdebug(json.dumps(data, indent=4, sort_keys=True))

        except TypeError as e:
            rospy.logerr('TypeError {}'.format(e))
        except KeyError as e:
            rospy.logerr('KeyError {}'.format(e))
        except SyntaxError as e:
            rospy.logerr('SyntaxError {}'.format(e))
        except NameError as e:
            rospy.logerr('NameError {}'.format(e))

        return 'succeeded'

    def coord2addres(self, lon, lat):
        # lon = x
        # lat = y
        header = {"Authorization": str("KakaoAK " + self.KaKaoRestAPIKey)}
        url = self.Host + self.APIAddr + "&x=" + str(lon) + "&y=" + str(lat)
        res = requests.get(url, headers=header)
        if res.status_code == 200:
            addr = res.json()
            rospy.logdebug(json.dumps(addr, indent=4, sort_keys=True))
            region1 = addr['documents'][0]['address']['region_1depth_name']
            region2 = addr['documents'][0]['address']['region_2depth_name']
            region3 = addr['documents'][0]['address']['region_3depth_name']
            print(region1.encode('utf-8'), region2.encode('utf-8'), region3.encode('utf-8'))

            if len(region1) == 3:
                region1 = region1[:-1]
            elif len(region1) > 3:
                region1 = region1[:2]

        return region1, region3

    def DetectNearCites(self, sido, stationName):
        # 현재 주소를 TM 체계의 좌표로 바꾸기 위한 API 주소
        GetTMPositon_API = 'http://openapi.airkorea.or.kr/openapi/services/rest/MsrstnInfoInqireSvc/getTMStdrCrdnt'
        # TM 체계의 주소로 가까운 측정소의 위치를 찾기 위한 API 주소
        GetNearDetector_API = 'http://openapi.airkorea.or.kr/openapi/services/rest/MsrstnInfoInqireSvc/getNearbyMsrstnList'

        # 1. 좌표를 얻은 "동"이름으로 TM 좌표를 얻음.
        GetTMURL = GetTMPositon_API + "?ServiceKey=" + self.dust_api_keys + "&umdName=" + stationName
        GetTMres = requests.get(GetTMURL)
        # if GetTMres.status_code == 200:
        #     print(GetTMres.text.encode('utf-8'))
        #     TMDataList = self.xml2Dict(GetTMres.text)['response']['body']['items']['item']
        # else:
        #     return False
        if GetTMres.status_code == 200:
            TMDataList = self.xml2Dict(GetTMres.text)
            if TMDataList['response']['body']['items'] is None:
                return False
            else:
                TMDataList = self.xml2Dict(GetTMres.text)['response']['body']['items']['item']
        else:
            return False

        tmX = tmY = None
        # 해당 동이 포함된 리스트를 탐색
        # print(type(TMDataList))
        newobj = []
        if isinstance(TMDataList, dict):
            newobj.append(TMDataList)
        else:
            newobj = TMDataList

        found = False
        for sidoindex in newobj:
            if sidoindex['sidoName'][:2] == sido:
                found = True
                tmX = sidoindex['tmX']
                tmY = sidoindex['tmY']
                break
        if not found:
            rospy.logerr('not found sidoName')

        # 2. 이렇게 얻은 tmX,tmY 좌표를 이용하여, 가까운 측정소 탐색
        GetStationURL = GetNearDetector_API + "?ServiceKey=" + self.dust_api_keys + "&tmX=" + tmX + "&tmY=" + tmY
        GetStationres = requests.get(GetStationURL)

        StationList = []
        if GetStationres.status_code == 200:
            NearStationsList = self.xml2Dict(GetStationres.text)['response']['body']['items']['item']

            for StationIndex in NearStationsList:
                StationList.append(StationIndex['stationName'])
            return StationList

        return False

    def Data2Dict(self, xmlDict):
        resultDict = {}
        infoList = xmlDict['response']['body']['items']['item']

        for stationIndex in infoList:
            resultDict.setdefault(stationIndex['stationName'], {})

            resultDict[stationIndex['stationName']].setdefault('o3Grade', stationIndex['o3Grade'])
            resultDict[stationIndex['stationName']].setdefault('pm10Grade', stationIndex['pm10Grade1h'])
            resultDict[stationIndex['stationName']].setdefault('pm25Grade', stationIndex['pm25Grade1h'])
            resultDict[stationIndex['stationName']].setdefault('no2Grade', stationIndex['no2Grade'])

        return resultDict

    def DustNOzoneInfo(self, lon, lat):
        # 미세먼지 탐색을 위한, API 경로
        dustApiAddr = 'http://openapi.airkorea.or.kr/openapi/services/rest/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty'

        # params 옵션을 이용한 인자 전달 시, 서비스 키가 지속적으로 변경되는 문제가 발생. 따라서 메뉴얼적인 문자 조합으로 조회 수행
        # params = {'serviceKey': self.dust_api_keys, 'numOfRows':10, 'pageNo':1, 'sidoName':sido, 'ver':1.3}

        sido, stationName = self.coord2addres(lon, lat)
        print(sido.encode('utf-8'), stationName.encode('utf-8'))
        targetStation = self.DetectNearCites(sido, stationName)
        # print( sido, stationName )
        # 주소를 찾지 못할 경우
        # if sido == False:
        #    return False

        url = dustApiAddr + "?serviceKey=" + self.dust_api_keys + "&sidoName=" + sido + "&ver=" + str(1.3)
        res = requests.get(url)

        """
        grade값을 4점으로 구성되며, 표는 아래와 같다.
        ______________________________________
        | 등 급 | 좋 음 | 보 통 | 나 쁨 | 매우 나쁨 |
        ______________________________________
        |garade|  1   |  2  |   3  |    4    |
        ______________________________________
        """

        if res.status_code == 200:
            station_info = self.xml2Dict(res.text)
            Dict_StationInfo = self.Data2Dict(station_info)

            for key in Dict_StationInfo.keys():
                print(key.encode('utf-8'))

            print('-----------------------')
            '''
            for targetStationIndex in targetStation:
                print(targetStationIndex.encode('utf-8'))
                if targetStationIndex in Dict_StationInfo.keys():
                    return Dict_StationInfo[targetStationIndex]
            # if not found
            for key in Dict_StationInfo.keys():
                return Dict_StationInfo[key]
            '''
            if targetStation is False:
                for StationInfoIndex in Dict_StationInfo:
                    if Dict_StationInfo[StationInfoIndex]['o3Grade'] is not None and Dict_StationInfo[StationInfoIndex]['pm10Grade'] is not None and \
                       Dict_StationInfo[StationInfoIndex]['pm25Grade'] is not None and Dict_StationInfo[StationInfoIndex]['no2Grade'] is not None:
                        return Dict_StationInfo[StationInfoIndex]

            else:
                # 목록에 같은 동이 있을 경우.
                if stationName in Dict_StationInfo.keys() and Dict_StationInfo[stationName]['o3Grade'] is not None and Dict_StationInfo[stationName]['pm10Grade'] is not None and Dict_StationInfo[stationName]['pm25Grade1h'] is not None and Dict_StationInfo[stationName]['no2Grade'] is not None:
                    return Dict_StationInfo[stationName]
                else:
                    for StationInfoIndex in Dict_StationInfo:
                        if Dict_StationInfo[StationInfoIndex]['o3Grade'] is not None and Dict_StationInfo[StationInfoIndex]['pm10Grade'] is not None and Dict_StationInfo[StationInfoIndex]['pm25Grade'] is not None and Dict_StationInfo[StationInfoIndex]['no2Grade'] is not None:
                            return Dict_StationInfo[StationInfoIndex]

        return False

    def xml2Dict(self, xml):
        list2xml = xmltodict.parse(xml)
        list2json = json.dumps(list2xml)
        result = json.loads(list2json)

        return result
