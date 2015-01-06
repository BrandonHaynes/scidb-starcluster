import os
import getpass
from setuptools import setup
from setuptools.command.install import install

plugin_name = 'scidbplugin.py'
config_name = 'scidbcluster.config'


class RegisterPluginDecorator(install):
    def run(self):
        install.run(self)

        config_filename = '~/.starcluster/config'
        config = self.get_config(config_filename)
        if not 'INCLUDE=~/.starcluster/' + config_name in config:
            print 'Adding include to ' + config_filename
            self.add_include(config, config_filename)

        self.set_keyname('~/.starcluster/' + config_name)

    @staticmethod
    def get_config(path):
        with open(os.path.expanduser(path), 'r') as file:
            return file.read()

    @staticmethod
    def add_include(config, path):
        insertion = '[global]\nINCLUDE=~/.starcluster/{}\n'.format(config_name)
        if '[global]' in config:
            config = config.replace('[global]', insertion)
        else:
            config = insertion + config
        with open(os.path.expanduser(path), 'w') as file:
            file.write(config)

    @staticmethod
    def set_keyname(path):
        config = RegisterPluginDecorator.get_config(path)
        config = config.replace('KEYNAME = AWSKey', 'KEYNAME = {}Key'.format(getpass.getuser()))
        with open(os.path.expanduser(path), 'w') as file:
            file.write(config)


setup(
    name='SciDB-Starcluster',
    version=1.0,
    url='https://github.com/BrandonHaynes/scidb-starcluster',
    author='Brandon Haynes',
    author_email='bhaynes@cs.washington.edu',
    description=('A SciDB source installation plugin for Starcluster.'),
    license='BSD',
    include_package_data=True,
    packages=[],
    scripts=[plugin_name],
    data_files=[(os.path.expanduser('~/.starcluster/plugins'), [plugin_name]),
                (os.path.expanduser('~/.starcluster'), [config_name])],
    install_requires=['StarCluster >= 0.95.6'],
    cmdclass={'install': RegisterPluginDecorator},
)
