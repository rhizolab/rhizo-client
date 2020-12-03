import os
import base64
import hashlib
import datetime


# parse an ISO formatted timestamp string, converting it to a python datetime object;
# note: this function is also defined in server code
def parse_json_datetime(json_timestamp):
    assert json_timestamp.endswith('Z')
    format = ''
    if '.' in json_timestamp:
        format = '%Y-%m-%dT%H:%M:%S.%f'
    else:
        format = '%Y-%m-%dT%H:%M:%S'
    if json_timestamp.endswith(' Z'):
        format += ' Z'
    else:
        format += 'Z'
    return datetime.datetime.strptime(json_timestamp, format)


# build an auth_code string by hashing a secret key
def build_auth_code(secret_key):
    nonce = base64.b64encode(os.urandom(32)).decode()
    key_hash = base64.b64encode(hashlib.sha512((nonce + ';' + secret_key).encode()).digest()).decode()
    key_part = secret_key[:3] + secret_key[-3:]
    return key_part + ';' + nonce + ';' + key_hash
