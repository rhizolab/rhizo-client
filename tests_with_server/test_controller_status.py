import json
import random
import datetime
from rhizo.main import c
from rhizo.util import parse_json_datetime


# send watchdog message and check that watchdog timestamp has updated
def test_controller_watchdog():
    c.send_message('watchdog', {})
    c.sleep(2)  # give controller some time to send the message
    own_path = c.path_on_server()
    (own_parent, own_name) = own_path.rsplit('/', 1)
    print('own path: %s' % own_path)
    print('own parent: %s' % own_parent)
    print('own name: %s' % own_name)
    file_list = c.resources.list_files(own_parent, type='controller_folder')  # get list of controllers
    print('controllers: %s' % len(file_list))
    for file_info in file_list:
        if file_info['name'] == own_name:
            wd_time = parse_json_datetime(file_info['last_watchdog_timestamp'])
            delta = datetime.datetime.utcnow() - wd_time
            print('watchdog time difference: %.2f' % delta.total_seconds())
            assert abs(delta.total_seconds()) < 60


# update controller status and check that it has been updated
def test_controller_status():
    test_str = 'test%06d' % random.randint(0, 999999)
    own_path = c.path_on_server()
    (own_parent, own_name) = own_path.rsplit('/', 1)
    print('own path: %s' % own_path)
    print('own parent: %s' % own_parent)
    print('own name: %s' % own_name)
    print('setting status: %s' % test_str)
    c.resources.send_request_to_server('PUT',  '/api/v1/resources' + own_path, {'status': json.dumps({'foo': test_str})})
    file_list = c.resources.list_files(own_parent, type='controller_folder')  # get list of controllers
    for file_info in file_list:
        if file_info['name'] == own_name:
            status = file_info['status']['foo']
            print('received status: %s' % status)
            assert status == test_str


# if run as a top-level script
if __name__ == '__main__':
    test_controller_watchdog()
    test_controller_status()
