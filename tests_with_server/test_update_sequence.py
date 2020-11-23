import random
import base64
import logging
from io import BytesIO
import gevent
from PIL import Image
from rhizo.main import c
from rhizo.resources import ResourceClient


# test updating basic sequences
def test_update_sequence():
    v = random.randint(1, 100)
    test_val1 = 'foo-%d' % v
    test_val2 = 'bar-%d' % v
    c.sequences.update(c.path_on_server() + '/test', test_val1, use_websocket=True)
    c.sequences.update(c.path_on_server() + '/testIntSeq', v, use_websocket=True)
    c.sequences.update('testFloatSeq', v + 0.5, use_websocket=True)
    c.sequences.update('folder/testSub', test_val2, use_websocket=True)
    logging.info('updated sequences (%d)' % v)
    gevent.sleep(10)  # wait so outbound messages are sent

    # read back using resource client
    if True:
        resource_client = ResourceClient(c.config)
        assert test_val1 == resource_client.read_file(c.path_on_server() + '/test').decode()
        assert test_val2 == resource_client.read_file(c.path_on_server() + '/folder/testSub').decode()
        assert v == int(resource_client.read_file(c.path_on_server() + '/testIntSeq').decode())
        assert round(v + 0.5, 2) == round(float(resource_client.read_file(c.path_on_server() + '/testFloatSeq').decode()), 2)


# test updating basic sequences
def test_update_multi():
    for use_message in [False, True]:
        v = random.randint(1, 100)
        test_val1 = 'foo-%d' % v
        test_val2 = 'bar-%d' % v
        c.sequences.update_multiple({'test': test_val1, 'testIntSeq': v, 'testFloatSeq': v + 0.5}, use_message=use_message)
        logging.info('updated multi sequences (%d)' % v)
        gevent.sleep(10)  # wait so outbound messages are sent
        resource_client = ResourceClient(c.config)
        assert test_val1 == resource_client.read_file(c.path_on_server() + '/test').decode()
        assert v == int(resource_client.read_file(c.path_on_server() + '/testIntSeq').decode())
        assert round(v + 0.5, 2) == round(float(resource_client.read_file(c.path_on_server() + '/testFloatSeq').decode()), 2)


# test updating an image sequence
def _test_send_image():
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    width = 320
    height = 240
    image = Image.new('RGB', (width, height))
    pixel_data = image.load()
    for y in range(height):
        for x in range(width):
            pixel_data[x, y] = (r, g, b)
    contents = encode_image(image)
    c.sequences.update('image', contents, use_websocket=False)
    logging.info('updated image (%d, %d, %d)' % (r, g, b))
    gevent.sleep(2)  # wait so outbound messages are sent

    # read back using resource client
    if False:
        resource_client = ResourceClient(c.config)
        contents = resource_client.read_file(c.path_on_server() + '/image')
        open('test.jpg', 'w').write(contents)


# check the path_on_server function
def test_path_on_server():
    assert c.config.server_test_path == c.path_on_server()


# encode a PIL image as a base64 string
def encode_image(image, format='JPEG'):
    return base64.b64encode(image_data(image, format)).decode()  # want string output, not bytes


# get image data as a jpeg (or other format) image file (raw binary data)
def image_data(image, format='JPEG'):
    mem_file = BytesIO()
    image.save(mem_file, format=format)
    data = mem_file.getvalue()
    mem_file.close()
    return data


# if run as a top-level script
if __name__ == '__main__':
    test_update_sequence()
    test_update_multi()
    # test_send_image()
