import random
import base64
import logging
from io import BytesIO
import gevent
from PIL import Image, ImageDraw


# The CameraDevice class represents a connection to camera hardware.
# It provides a consistent interface to several camera libraries.
class CameraDevice(object):

    # initialize a camera connection using parameters in the given config
    def __init__(self, config):
        pass

    # close the connection to the camera
    def close(self):
        pass

    # returns true if the camera is connected
    def is_connected(self):
        pass

    # capture and save an image as a jpeg file on the local file system
    def save_image(self, file_name):
        pass

    # capture an image from the camera and return an image object (PIL image)
    def capture_image(self):
        pass


## The SimCameraDevice class provides a simulated camera for testing.
class SimCameraDevice(object):

    # initialize a camera connection using parameters in the given config
    def __init__(self, config):
        self.width = config.get('width', 960)
        self.height = config.get('height', 720)
        self.frame_index = 0
        self.opened = True
        self.image = None
        if 'image' in config:
            self.image = Image.open(config.image).resize((self.width, self.height))

    # close the connection to the camera
    def close(self):
        assert self.opened
        self.opened = False

    # returns true if the camera is connected
    def is_connected(self):
        return self.opened

    # capture and save an image as a jpeg file on the local file system
    def save_image(self, file_name):
        assert self.opened
        pass

    # capture an image from the camera and return an image object (PIL image)
    def capture_image(self):
        assert self.opened
        if self.image:
            image = self.image.copy()
        else:
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            image = Image.new('RGB', (self.width, self.height))
            pixel_data = image.load()
            for y in xrange(self.height):
                for x in xrange(self.width):
                    pixel_data[x, y] = (r, g, b)
        drawer = ImageDraw.Draw(image)
        drawer.text((10, 10), '%d' % self.frame_index)  # a diagnostic indicator so that we know we're getting live/changing images
        drawer.text((10, 30), '*' * (self.frame_index % 20))  # a diagnostic indicator so that we know we're getting live/changing images
        self.frame_index += 1
        return image


## The PiCameraDevice class connects to a Raspberry Pi camera using the picamera library.
class PiCameraDevice(object):

    # initialize a camera connection using parameters in the given config
    def __init__(self, config, warn_on_error = True):
        try:
            import picamera
            self.camera = picamera.PiCamera()
        except:
            self.camera = None
            if warn_on_error:
                logging.warning('unable to open Pi camera')
        if 'width' in config and 'height' in config:
            self.camera.resolution = (config.width, config.height)
        if 'exposure_mode' in config:
            self.camera.exposure_mode = config.exposure_mode
        if 'awb_mode' in config:
            self.camera.awb_mode = config.awb_mode
        if 'red_gain' in config and 'blue_gain' in config:
            self.camera.awb_gains = (config.red_gain, config.blue_gain)
        if 'shutter_speed' in config:
            self.camera.shutter_speed = config.shutter_speed
        self.jpeg_quality = config.get('jpeg_quality', 10)

    # close the connection to the camera
    def close(self):
        self.camera.close()
        self.camera = None

    # returns true if the camera is connected
    def is_connected(self):
        return True if self.camera else False

    # capture and save an image as a jpeg file on the local file system
    def save_image(self, file_name):
        from picamera import PiCameraRuntimeError
        while True:
            try:
                self.camera.capture(file_name, format='jpeg', quality=self.jpeg_quality)
                break
            except PiCameraRuntimeError:
                logging.warning('camera error; will try again')
                gevent.sleep(2)

    # capture an image from the camera and return an image object (PIL image)
    def capture_image(self):
        from picamera import PiCameraRuntimeError
        while True:
            try:
                stream = BytesIO()
                self.camera.capture(stream, format='jpeg', quality=self.jpeg_quality)
                break
            except PiCameraRuntimeError:
                logging.warning('camera error; will try again')
                gevent.sleep(2)
        stream.seek(0)
        return Image.open(stream)


## The USBCameraDevice class connects to a USB camera using the pygame library.
class USBCameraDevice(object):

    # initialize a camera connection using parameters in the given config
    def __init__(self, config, warn_on_error = True):
        import pygame.camera
        pygame.camera.init()
        camera_list = pygame.camera.list_cameras()
        if camera_list:
            self.camera = pygame.camera.Camera(camera_list[0])  # connect to first camera
            self.camera.start()
        else:
            if warn_on_error:
                logging.warning('unable to open USB camera')
            self.camera = None

    # close the connection to the camera
    def close(self):
        import pygame.camera
        pygame.camera.quit()
        self.camera = None

    # returns true if the camera is connected
    def is_connected(self):
        return True if self.camera else False

    # capture and save an image as a jpeg file on the local file system
    def save_image(self, file_name):
        import pygame.image  # fix(faster): can we move/remove this
        for i in range(3):  # fix(later): requires 3 captures to get latest image
            img = self.camera.get_image()
        pygame.image.save(img, file_name)

    # capture an image from the camera and return an image object (PIL image)
    def capture_image(self):
        import pygame.image  # fix(faster): can we move/remove this
        for i in range(3):  # fix(later): requires 3 captures to get latest image
            img = self.camera.get_image()
        image_data = pygame.image.tostring(img, 'RGBA', False)
        return Image.fromstring('RGBA', img.size, image_data)


## The Camera extension supports connecting to one or more camera devices.
class Camera(object):

    def __init__(self, controller):
        self._controller = controller
        self.device = None

    # open a camera using a config object; defaults to using "camera" config within main controller config
    def open(self, config = None):
        if not config:
            config = self._controller.config.camera
        type = config.type
        print('adding camera: %s' % type)
        if type == 'sim':
            self.device = SimCameraDevice(config)
        elif type == 'pi':
            self.device = PiCameraDevice(config)
        elif type == 'usb':
            self.device = USBCameraDevice(config)


# ======== CAMERA/IMAGING UTILITY FUNCTIONS ========


# encode a PIL image as a base64 string
def encode_image(image, format='JPEG'):
    return base64.b64encode(image_data(image, format))


# get image data as a jpeg (or other format) image file (raw binary data)
def image_data(image, format='JPEG'):
    mem_file = BytesIO()
    image.save(mem_file, format=format)
    data = mem_file.getvalue()
    mem_file.close()
    return data
