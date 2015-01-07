import os
import getpass
import re
from setuptools import setup
from setuptools.command.install import install

plugin_name = 'scidbplugin.py'
config_name = 'scidbcluster.config'
config_path = '~/.starcluster'

class RegisterPluginDecorator(install):
    def run(self):
        install.run(self)

        self.ensure_include(config_name, config_path)
        self.set_keyname(os.path.join(config_path, config_name))

    def ensure_include(self, name, path, root='config'):
        filename = os.path.join(path, root)
        config = self.get_config(filename)

        if not self.already_included(name, config):
            print 'Adding include to ' + filename
            self.add_include(config, filename)
        else:
            print 'Root configuration already appears to include ' + filename

    @staticmethod
    def get_config(path):
        with open(os.path.expanduser(path), 'r') as file:
            return file.read()

    @staticmethod
    def already_included(config_name, config):
        return re.search(r'^INCLUDE\w*=\w*.*' + re.escape(os.path.join(config_path, config_name)),
                         config, 
                         flags=re.IGNORECASE | re.MULTILINE)

    @staticmethod
    def add_include(config, path):
        insertion = 'INCLUDE={}'.format(os.path.join(config_path, config_name))

        # No global section
        if not '[global]' in config:
            config = '[global]\n{}\n{}'.format(insertion, config)
        # Global section with existing INCLUDE pair
        elif re.search(r'^INCLUDE\w*=\w*', config, flags=re.IGNORECASE | re.MULTILINE):
            config = re.sub(r'^INCLUDE\w*=\w*', insertion + ',', config, flags=re.IGNORECASE | re.MULTILINE)
        # Global section, no INCLUDE pair
        else:
            config = config.replace('[global]', '[global]\n' + insertion)

        with open(os.path.expanduser(path), 'w') as file:
            file.write(config)

    @staticmethod
    def set_keyname(path):
        username = os.getenv("SUDO_USER") or getpass.getuser()
        config = RegisterPluginDecorator.get_config(path)
        config = config.replace('KEYNAME = AWSKey', 'KEYNAME = {}Key'.format(username))
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
    scripts=[],
    data_files=[(os.path.expanduser('~/.starcluster/plugins'), [plugin_name]),
                (os.path.expanduser('~/.starcluster'), [config_name])],
    install_requires=['StarCluster >= 0.95.6'],
    cmdclass={'install': RegisterPluginDecorator},
)
