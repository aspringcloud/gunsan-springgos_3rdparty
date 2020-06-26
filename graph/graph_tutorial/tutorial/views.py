# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from tutorial.auth_helper import get_sign_in_url, get_token_from_code, store_token, store_user, remove_user_and_token, get_token
from tutorial.graph_helper import get_user, get_calendar_events
import dateutil.parser

# utils
import threading
import time
import logging
# fsm
import smach
import py_trees
# kafka
import kafka
logging.basicConfig(level=logging.INFO, format='%(asctime)s (%(threadName)-2s) %(message)s',)

# test
import json
from django.core.mail import send_mail

#===================== smach =========================

def init_blackboard():
  blackboard = py_trees.blackboard.Blackboard()
  blackboard.pid = None
  blackboard.dtg = {}
  blackboard.event = {}
  blackboard.osmurl = ''
  blackboard.camurl = ''
  return blackboard

  
def loginfo(msg):
    logging.info(msg)

def logwarn(msg):
    logging.warning(msg)

def logdebug(msg):
    logging.debug(msg)

def logerr(msg):
    logging.error(msg)


class preempted_timeout(smach.State):
  def __init__(self, timeout):
    smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                          input_keys=['blackboard'],
                          output_keys=['blackboard'])
    self.timeout = timeout

  def execute(self, ud):
    start_time = time.time()
    while True:
        if self.preempt_requested():
            self.service_preempt()
            return 'preempted'
        time.sleep(0.01)
        if time.time() - start_time > self.timeout:
            break
    return 'succeeded'

class dummy(smach.State):
    def __init__(self, full_path, expected_state):
        smach.State.__init__(self, outcomes=['succeeded', 'preempted', 'aborted'],
                             input_keys=['blackboard'],
                             output_keys=['blackboard'])
        self.full_path = full_path
        self.expected_state = expected_state

    def execute(self, ud):
        logging.info('dummy')
        token = get_token_from_code(self.full_path, self.expected_state)
        logging.info(token)
        return 'succeeded'

def main(get_full_path, expected_state, token):
  smach.set_loggers(loginfo,logwarn,logdebug,logerr) # disable
  top = smach.StateMachine(outcomes=['succeeded', 'preempted', 'aborted'])
  top.userdata.blackboard = init_blackboard()
  with top:        
      smach.StateMachine.add('start', preempted_timeout(5.0), {'succeeded': 'dummy'})
      smach.StateMachine.add('dummy', dummy(get_full_path, expected_state), {'succeeded': 'succeeded'})
      
  outcome = top.execute()


# <HomeViewSnippet>
def home(request):
  context = initialize_context(request)  
  return render(request, 'tutorial/home.html', context)
# </HomeViewSnippet>

# <InitializeContextSnippet>
def initialize_context(request):
  context = {}

  # Check for any errors in the session
  error = request.session.pop('flash_error', None)

  if error != None:
    context['errors'] = []
    context['errors'].append(error)

  # Check for user in the session
  context['user'] = request.session.get('user', {'is_authenticated': False})
  return context
# </InitializeContextSnippet>

# <SignInViewSnippet>
def sign_in(request):
  # Get the sign-in URL
  sign_in_url, state = get_sign_in_url()
  # Save the expected state so we can validate in the callback
  request.session['auth_state'] = state
  # Redirect to the Azure sign-in page
  return HttpResponseRedirect(sign_in_url)
# </SignInViewSnippet>

# <SignOutViewSnippet>
def sign_out(request):
  # Clear out the user and token
  remove_user_and_token(request)  
  return HttpResponseRedirect(reverse('home'))
# </SignOutViewSnippet>

# <CallbackViewSnippet>
def callback(request):
  # Get the state saved in session
  expected_state = request.session.pop('auth_state', '')
  # Make the token request  
  token = get_token_from_code(request.get_full_path(), expected_state)
  
  # start smach thread
  logging.debug('Starting smach')
  main_thread = threading.currentThread()
  started = False
  for t in threading.enumerate():
    if t is main_thread:
        continue
    logging.info('joining %s', t.getName())
    if t.getName() == 'smach':
      started = True
  if not started:
    # 인자값으로 request해야 한다. 몇시간동안 하나의 token가지고 호출이 가능하므로 아래는 필요 없다. 
    threading.Thread(name='smach', target=main, args=(request.get_full_path(), expected_state, token)).start()

  # Get the user's profile
  user = get_user(token)

  # Save token and user
  store_token(request, token)
  store_user(request, user)

  return HttpResponseRedirect(reverse('home'))
# </CallbackViewSnippet>

# <CalendarViewSnippet>
def calendar(request):
  message_body = 'Use this link to log in'
  send_mail(
      'Your login link for Superlists',
      message_body,
      'bcchoi@aspringcloud.com',
      ['zaxrok@gmail.com'],
      fail_silently=False,
  )

  context = initialize_context(request)

  token = get_token(request)

  events = get_calendar_events(token)
  print(json.dumps(events, indent=4, sort_keys=True))

  if events:
    # Convert the ISO 8601 date times to a datetime object
    # This allows the Django template to format the value nicely
    for event in events['value']:
      event['start']['dateTime'] = dateutil.parser.parse(event['start']['dateTime'])
      event['end']['dateTime'] = dateutil.parser.parse(event['end']['dateTime'])

    context['events'] = events['value']

  return render(request, 'tutorial/calendar.html', context)
# </CalendarViewSnippet>


# <EmailViewSnippet>
def email(request):
  start_time = time.time()
  message_body = 'Use this link to log in'
  from_email = 'bcchoi@aspringcloud.com'
  to_email = ['zaxrok@gmail.com']
  send_mail(
     'Your login link for Superlists',
      message_body,
      from_email,
      to_email,
      fail_silently=False,
  )
  elapsed_time = time.time() - start_time
  context = {
    'elapsed_time':elapsed_time,
    'message_body': message_body,
    'from_email':from_email,
    'to_emai': to_email
  }
 
  return render(request, 'tutorial/email.html', context)
# </EmailViewSnippet>
