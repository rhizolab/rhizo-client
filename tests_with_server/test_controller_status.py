import json
import random
import datetime
import pytest
import gevent
from rhizo.controller import Controller
from rhizo.util import parse_json_datetime



@pytest.fixture
def controller():
    return Controller()


# send watchdog message and check that watchdog timestamp has updated
def test_controller_watchdog(controller):
    controller.send_message('watchdog', {})
    gevent.sleep(2)  # give controller some time to send the message
    own_path = controller.path_on_server()
    (own_parent, own_name) = own_path.rsplit('/', 1)
    print('own path: %s' % own_path)
    print('own parent: %s' % own_parent)
    print('own name: %s' % own_name)
    file_list = controller.files.list_files(own_parent, type='controller_folder')  # get list of controllers
    print('controllers: %s' % len(file_list))
    for file_info in file_list:
        if file_info['name'] == own_name:
            wd_time = parse_json_datetime(file_info['last_watchdog_timestamp'])
            delta = datetime.datetime.utcnow() - wd_time
            print('watchdog time difference: %.2f' % delta.total_seconds())
            assert abs(delta.total_seconds()) < 60


# update controller status and check that it has been updated
def test_controller_status(controller):
    test_str = 'test%06d' % random.randint(0, 999999)
    own_path = controller.path_on_server()
    (own_parent, own_name) = own_path.rsplit('/', 1)
    print('own path: %s' % own_path)
    print('own parent: %s' % own_parent)
    print('own name: %s' % own_name)
    print('setting status: %s' % test_str)
    controller.files.send_request_to_server('PUT', '/api/v1/resources' + own_path, {'status': json.dumps({'foo': test_str})})
    file_list = controller.files.list_files(own_parent, type='controller_folder')  # get list of controllers
    for file_info in file_list:
        if file_info['name'] == own_name:
            status = file_info['status']['foo']
            print('received status: %s' % status)
            assert status == test_str


# if run as a top-level script
if __name__ == '__main__':
    c = Controller()
    test_controller_watchdog(c)
    test_controller_status(c)
