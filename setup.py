from setuptools import setup
import pathlib

here = pathlib.Path(__file__).parent.resolve()
with open(str(here / 'README.md')) as f:
    long_description = f.read()

setup(
    name='rhizo-client',
    version='0.1.1',
    description='Client for rhizo-server',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/rhizolab/rhizo-client',
    author='Peter Sand',
    author_email='rhizo@rhizolab.org',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    install_requires=[
        'gevent',
        'paho-mqtt',
        'psutil',
        'pyyaml>=5',
        'ws4py',
    ],
    license='MIT',
    packages=['rhizo'],
    python_requires='>=2.7, <4',
    package_data={
        'rhizo': ['sample_config.yaml'],
    },
)
