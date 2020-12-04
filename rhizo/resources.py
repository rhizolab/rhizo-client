import os
import gevent
import base64
import json
import ssl
import urllib
try:
    from httplib import HTTPConnection, HTTPSConnection
except ModuleNotFoundError:
    from http.client import HTTPConnection, HTTPSConnection
import logging
from io import StringIO
from rhizo.util import build_auth_code


# an exception type for API errors
class ApiError(Exception):
    def __init__(self, status, reason, data):
        self.status = status
        self.reason = reason
        self.data = data
    def __str__(self):
        return 'API error; status: %d, reason: %s, data: %s' % (self.status, self.reason, self.data)


# the WriteFileWrapper allows creating a remote file that behaves like a normal python file object (currently just implementing write() and close())
class WriteFileWrapper(object):

    # creates a buffer (StringIO instance) that will store data before it is sent to the server
    def __init__(self, full_server_file_name, resource_client):
        self._full_server_file_name = full_server_file_name
        self._resource_client = resource_client
        self._file_obj = StringIO()
        self._closed = False

    # write data into the buffer
    def write(self, data):
        assert not self._closed
        self._file_obj.write(data)

    # sends buffer to the server
    def close(self):
        if not self._closed:
            self._resource_client.write_file(self._full_server_file_name, self._file_obj.getvalue())
            self._closed = True

    # nothing here
    def __enter__(self):
        pass

    # sends buffer to the server
    def __exit__(self, type, value, traceback):
        if not self._closed:
            self.close()


# the FileClient class is used to access the resource API provided by the server
class FileClient(object):

    # store information from configuration file
    def __init__(self, config, controller = None):
        if 'secret_key' in config:
            self._secret_key = config.secret_key
        else:
            logging.info('no secret key in config')
            self._secret_key = 'x'  # we may not have a secret key if we haven't yet requested one from server
        self._server_name = config.server_name
        if 'ssl_skip_verify' in config:
            self._ssl_skip_verify = config.ssl_skip_verify
        else:
            self._ssl_skip_verify = False

        if 'secure_server' in config:
            self._secure_server = config.secure_server
        else:
            host_name = config.server_name.split(':')[0]
            self._secure_server = host_name != 'localhost' and host_name != '127.0.0.1'
        self._enable_cache = config.get('enable_cache', False)
        self._controller = controller

        # some aliases for compatibility
        self.list_files = self.list
        self.file_exists = self.exists
        self.file_info = self.info
        self.read_file = self.read
        self.write_file = self.write

    # get a list of files from the server;
    # each item in the list is a dictionary with the resource name and other meta-data
    def list(self, dir_path, recursive = False, type = None, filter = None, extended = False):
        assert dir_path.startswith('/')
        params = {'extended': int(extended)}
        if recursive:
            params['recursive'] = recursive
        if type:
            params['type'] = type
        if filter:
            params['filter'] = filter
        data = self.send_request_to_server('GET', '/api/v1/resources' + dir_path, params)
        return json.loads(data)

    # returns boolean indicating whether file exists (or raises ApiError on permission failure or other error)
    def exists(self, file_name):
        assert file_name.startswith('/')
        file_name = file_name.replace(' ', '%20')  # fix(soon): use proper url encoding function instead
        try:
            self.send_request_to_server('GET', '/api/v1/resources' + file_name, {'meta': 1})
        except ApiError as e:
            if e.status == 404:
                return False
            else:
                raise e
        return True

    # returns a dictionary of info about a file
    def info(self, file_name):
        assert file_name.startswith('/')
        file_info = self.send_request_to_server('GET', '/api/v1/resources' + file_name, {'meta': 1, 'include_path': 1})
        return json.loads(file_info)

    # returns a file-like object for reading or writing
    # fix(soon): StringIO doesn't support "with" syntax; add a wrapper around it?
    def open(self, file_name, mode):
        if 'w' in mode:
            return WriteFileWrapper(file_name, self)
        else:
            return StringIO(self.read_file(file_name))

    # read a file from the server; returns data as bytes; if reading string from text file, use .decode() on returned value
    def read(self, file_path):
        assert file_path.startswith('/')
        data = None
        if self._enable_cache:
            cache_path = cache_load(file_path)
            if cache_path:
                data = open(cache_path, 'rb').read()
        else:
            data = self.retrieve_resource_data(file_path)
        return data

    # make sure the given resource data is stored in the local cache (retrieve it from server if needed);
    # returns path of file in local cache (relative to current directory)
    def cache_load(self, file_path):
        data = self.send_request_to_server('GET', '/api/v1/resources' + file_path, {'meta': 1})
        resource_info = json.loads(data)
        resource_id = resource_info['id']
        cache_path = 'cache/%d_%d.data' % (resource_info['id'], resource_info['lastRevisionId'])
        if not os.path.exists(cache_path):
            data = self.retrieve_resource_data(file_path)
            open(cache_path, 'wb').write(data)
        return cache_path

    # get a resource/file from the server
    def retrieve_resource_data(self, file_path):
        return self.send_request_to_server('GET', '/api/v1/resources' + file_path, {}, accept_binary = True)

    # create a folder on the server (can be used to create multiple levels at once); folder_path must be absolute (with leading slash)
    def create_folder(self, folder_path):
        assert folder_path.startswith('/')
        parts = folder_path.rsplit('/', 1)
        params = {
            'path': parts[0],
            'name': parts[1],
            'type': 10,  # fix(soon): change to string?
        }
        self.send_request_to_server('POST', '/api/v1/resources', params)

    # write a file to the server; contents can be string or bytes
    def write(self, file_path, contents, creation_timestamp = None, modification_timestamp = None, new_version = False):
        try:
            data = base64.b64encode(contents)  # handle bytes
        except:
            data = base64.b64encode(contents.encode())  # handle string
        file_info = {
            'data': data
        }
        if creation_timestamp:
            file_info['creationTimestamp'] = creation_timestamp.isoformat() + ' Z'
        if modification_timestamp:
            file_info['modificationTimestamp'] = modification_timestamp.isoformat() + ' Z'
        if new_version:

            # if file exists, do a PUT to the resource path
            try:
                self.send_request_to_server('GET', '/api/v1/resources' + file_path, file_info)
                self.send_request_to_server('PUT', '/api/v1/resources' + file_path, file_info)

            # if file doesn't exist, do a POST to create a new resource
            except ApiError as e:
                if e.status == 404:
                    parts = file_path.rsplit('/', 1)
                    file_info['path'] = parts[0]
                    file_info['name'] = parts[1]
                    file_info['type'] = 20  # fix(soon): change to string?
                    self.send_request_to_server('POST', '/api/v1/resources', file_info)
                else:
                    raise e
        else:
            self.send_request_to_server('POST', '/api/v1/resources' + file_path, file_info)

    # move a file to a new location
    def move(self, file_path, new_parent_path):
        params = {'parent': new_parent_path}
        self.send_request_to_server('PUT', '/api/v1/resources' + file_path, params)

    # this allows sending messages to folders using the REST API (as opposed to the usual websocket approach)
    def send_message(self, folder_path, message_type, parameters):
        message_info = {
            'folder_path': folder_path,
            'type': message_type,
            'parameters': json.dumps(parameters),
        }
        self.send_request_to_server('POST', '/api/v1/messages', message_info)

    # a utility function used by other methods to send an authenticated request to the server;
    # retries on comm error or server error;
    # returns response data if successful; raises an exception if not
    def send_request_to_server(self, method, path, params = None, accept_binary = False):
        if not params:
            params = {}
        accept_type = 'application/octet-stream' if accept_binary else 'text/plain'
        retry_count = 0

        # prepare authentication
        if self._controller and self._controller.config.get('old_auth', False):
#        if False:
            params['authCode'] = build_auth_code(self._secret_key)
            basic_auth = None
        else:
            if self._controller:  # fix(later): revisit this: can we still get a version/build if using stand-alone resource client?
                user_name = self._controller.VERSION + '.' + self._controller.BUILD  # send client version as user name
            else:
                user_name = 'resource_client'
            password = self._secret_key  # send secret key as password
            basic_auth = base64.b64encode(('%s:%s' % (user_name, password)).encode('utf-8')).decode()

        # make request and retry if there is an exception or server error
        while True:
            try:

                # if the request is valid, we can go ahead and return the data
                (status, reason, data) = send_request(self._server_name, method, path, params, self._secure_server, accept_type, basic_auth, self._ssl_skip_verify)
                if status == 200:
                    break
                err_text = '%d %s' % (status, reason)
            except Exception as e:  # fix(clean): the goal here is to catch errors in conn.getresponse() or response.read(); maybe we should move send_request code into this function and just try those two lines
                if retry_count > 100:  # if we've already retried many times, give up
                    raise e
                logging.debug('exception: %s' % e)
                err_text = str(e)
                status = None

            # if there's a problem with the request (e.g. 400/403/404) or we've already retried many times, raise an error
            if status and (status < 500 or retry_count > 100):
                raise ApiError(status, reason, data)

            # try again in 10 seconds
            logging.info('retrying %s %s; error: %s' % (method, path, err_text))
            gevent.sleep(10)
            retry_count += 1

        # if request was successful (status 200), return the data
        return data


# temporary alias for backward compatibility
ResourceClient = FileClient


# send an HTTP request to a server;
# returns response tuple: (response status, response reason, response data)
def send_request(server, method, path, params, secure = True, accept_type = 'text/plain', basic_auth = None, ssl_skip_verify = False):
    headers = {
        'Content-type': 'application/x-www-form-urlencoded',
        'Accept': accept_type,
    }
    if basic_auth:
        headers['Authorization'] = 'Basic %s' % basic_auth
    try:
        params = urllib.urlencode(params)
    except:  # python 3
        params = urllib.parse.urlencode(params)
    if secure:
        if ssl_skip_verify:
            conn = HTTPSConnection(server, context=ssl._create_unverified_context())
        else:
            conn = HTTPSConnection(server)
    else:
        conn = HTTPConnection(server)
    conn.request(method, path, params, headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return (response.status, response.reason, data)
