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

def init_blackboard():
    blackboard = py_trees.blackboard.Blackboard()
    blackboard.pid = None
    return blackboard


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
