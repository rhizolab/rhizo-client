import os
import math
import base64
import hashlib
import datetime
# math utility functions from Manylabs; MIT license


# join a relative file name / path with a base directory, attempting to make sure file location is not outside base directory
# fix(soon): deal with escape characters, etc.?
def safe_join(work_dir, rel_file_name):
    if '..' in rel_file_name or os.path.isabs(rel_file_name):
        return ''
    else:
        return work_dir + '/' + rel_file_name


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


# return a datetime object formatted as a string in the standard format
def datetime_to_str(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# ======== math functions ========


# compute median of a list/array of numbers
def median(data):
    sorted_data = sorted(data)
    count = len(sorted_data)
    if count % 2 == 1:
        return sorted_data[(count + 1) / 2 - 1]
    else:
        lower = sorted_data[count / 2 - 1]
        upper = sorted_data[count / 2]
        return float(lower + upper) / 2.0


# compute standard deviation of a list/array of numbers
def stdev(data, mean):
    sum_sq_diff = sum([(v - mean) * (v - mean) for v in data])
    return math.sqrt(sum_sq_diff / (len(data) - 1))


# compute mean of a list/array of numbers
def mean(data):
    return float(sum(data)) / float(len(data))


# try to convert a string to a number
# fix(clean): remove this after remove old config format
def convert_value(value):
    try:
        value = int(value)
    except:
        try:
            value = float(value)
        except:
            pass
    return value


# ======== checksum functions ========


# an implementation of the CRC16-CCITT algorithm; assumes message is an ascii string
def crc16_ccitt(message):
    crc = 0xFFFF
    for c in message:
        crc = crc16_update(crc, ord(c))
    return crc


# an implementation of the CRC16-CCITT algorithm; assumes data is an 8-bit value
def crc16_update(crc, data):
    data = data ^ (crc & 0xFF)
    data = data ^ ((data << 4) & 0xFF)
    return (((data << 8) & 0xFFFF) | ((crc >> 8) & 0xFF)) ^ (data >> 4) ^ (data << 3)


# ======== auth functions ========


# build an auth_code string by hashing a secret key
def build_auth_code(secret_key):
    nonce = base64.b64encode(os.urandom(32)).decode()
    key_hash = base64.b64encode(hashlib.sha512((nonce + ';' + secret_key).encode()).digest()).decode()
    key_part = secret_key[:3] + secret_key[-3:]
    return key_part + ';' + nonce + ';' + key_hash
