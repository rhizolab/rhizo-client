import random
import logging
from PIL import Image
from rhizo.main import c
from rhizo.extensions.camera import encode_image
from rhizo.extensions.resources import ResourceClient


# test updating basic sequences
def test_update_sequence():
    v = random.randint(1, 100)
    test_val1 = 'foo-%d' % v
    test_val2 = 'bar-%d' % v
    c.update_sequence(c.config.server_test_path + '/test', test_val1, use_websocket = False)
    c.update_sequence(c.config.server_test_path + '/testIntSeq', v, use_websocket = False)
    c.update_sequence('testFloatSeq', v + 0.5, use_websocket = True)
    c.update_sequence('folder/testSub', test_val2, use_websocket = True)
    logging.info('updated sequences (%d)' % v)
    c.sleep(5)  # wait so outbound messages are sent

    # read back using resource client
    if True:
        resource_client = ResourceClient(c.config)
        assert test_val1 == resource_client.read_file(c.config.server_test_path + '/test')
        assert test_val2 == resource_client.read_file(c.config.server_test_path + '/folder/testSub')
        assert v == int(resource_client.read_file(c.config.server_test_path + '/testIntSeq'))
        assert round(v + 0.5, 2) == round(float(resource_client.read_file(c.config.server_test_path + '/testFloatSeq')), 2)


# test updating an image sequence
def test_send_image():
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    width = 320
    height = 240
    image = Image.new('RGB', (width, height))
    pixel_data = image.load()
    for y in xrange(height):
        for x in xrange(width):
            pixel_data[x, y] = (r, g, b)
    contents = encode_image(image)
    c.update_sequence('image', contents)
    logging.info('updated image (%d, %d, %d)' % (r, g, b))
    c.sleep(2)  # wait so outbound messages are sent

    # read back using resource client
    if False:
        resource_client = ResourceClient(c.config)
        contents = resource_client.read_file(c.config.server_test_path + '/image')
        open('test.jpg', 'w').write(contents)


# check the path_on_server function
def test_path_on_server():
    assert c.config.server_test_path == c.path_on_server()


# if run as a top-level script
if __name__ == '__main__':
    test_update_sequence()
