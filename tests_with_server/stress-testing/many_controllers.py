import os
import json
import base64
import subprocess
import gevent
from rhizo.main import c


controller_count = 20


# initialize controllers
for i in range(controller_count):
    name = 'ctrl-%04d' % i
    print('preparing: %s' % name)

    # create local folder
    if not os.path.exists(name):
        os.mkdir(name)

    # create server folder
    server_path = c.path_on_server() + '/' + name
    if not c.files.file_exists(server_path):
        print('creating on server: %s' % server_path)
        params = {
            'parent': c.path_on_server(),
            'name': name,
            'type': 12,
        }
        data = c.files.send_request_to_server('POST', '/api/v1/resources', params)
        data = json.loads(data)
        new_id = data['id']
        params = {
            'access_as_controller_id': new_id,
        }
        data = c.files.send_request_to_server('POST', '/api/v1/keys', params)
        data = json.loads(data)
        print(data)
        secret_key = data['secret_key']

        # create config file
        config_file_name = name + '/config.yaml'
        open(config_file_name, 'w').write('server_name: %s\nsecret_key: %s\n' % (c.config.server_name, secret_key))


# launch controllers
for i in range(controller_count):
    name = 'ctrl-%04d' % i
    print('launching: %s' % name)
    os.chdir(name)
    p = subprocess.Popen('python ../each_controller.py')
    os.chdir('..')


# wait forever
while True:
    gevent.sleep(1)
