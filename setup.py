from setuptools import setup

setup(name='Quickscope',
      version='0.1.2',
      description='MC Sniping Application',
      author='daviga404',
      author_email='daviga404@gmail.com',
      packages=['quickscope'],
      scripts=['bin/quickscope'],
      include_package_data=True,
      install_requires=['python-digitalocean']
)
