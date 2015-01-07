import os
import random
import string
from starcluster.clustersetup import DefaultClusterSetup
from starcluster.logger import log

SCIDB_VERSION = 14.8
SCIDB_REVISION = 8628
#SCIDB_INSTALL_PATH = '/opt/scidb/$SCIDB_VER'

DEFAULT_USERNAME = 'scidb'
DEFAULT_REPOSITORY = 'https://github.com/BrandonHaynes/scidb.git'
DEFAULT_BRANCH = None
DEFAULT_SHIM_PACKAGE_URI = 'https://paradigm4.github.io/shim/shim_14.8_amd64.deb'
DEFAULT_DIRECTORY = '/mnt/scidb'
DEFAULT_CLIENTS = '0.0.0.0/0'
DEFAULT_BUILD_TYPE = 'RelWithDebInfo'
DEFAULT_BUILD_THREADS = 4

#http://www.scidb.org/forum/viewtopic.php?f=11&t=530
REQUIRED_PACKAGES = ['build-essential', 'cmake', 'libboost1.48-all-dev', 
                     'postgresql-8.4', 'libpqxx-3.1', 'libpqxx3-dev', 
                     'libprotobuf7', 'libprotobuf-dev', 'protobuf-compiler', 
                     'doxygen', 'flex', 'bison', 'libxerces-c-dev', 
                     'libxerces-c3.1', 'liblog4cxx10', 'liblog4cxx10-dev', 
                     'libcppunit-1.12-1', 'libcppunit-dev', 'libbz2-dev', 
                     'postgresql-contrib-8.4', 'libconfig++8', 
                     'libconfig++8-dev', 'libconfig8-dev', 'subversion', 
                     'libreadline6-dev', 'libreadline6', 'python-paramiko', 
                     'python-crypto', 'xsltproc', 'liblog4cxx10-dev',
                     'subversion', 'expect', 'openssh-server', 'openssh-client',
                     'git-svn', 'gdebi'] # Shim uses gdebi

class SciDBInstaller(DefaultClusterSetup):
    def __init__(self, 
                 username=DEFAULT_USERNAME,
                 password=''.join(random.sample(string.lowercase+string.digits, 20)),
                 repository=DEFAULT_REPOSITORY,
                 branch=DEFAULT_BRANCH,
                 shim_uri=DEFAULT_SHIM_PACKAGE_URI,
                 directory=DEFAULT_DIRECTORY,
                 clients=DEFAULT_CLIENTS,
                 build_type=DEFAULT_BUILD_TYPE,
                 build_threads=DEFAULT_BUILD_THREADS):
        super(SciDBInstaller, self).__init__()

        self.username = username
        self.password = password
        self.repository = repository
        self.branch = branch
        self.shim_uri = shim_uri
        self.directory = directory
        self.clients = clients
        self.build_type = build_type
        self.build_threads = build_threads

    def _set_up_node(self, node):
        log.info("1   Begin configuration {}".format(node.alias))

        log.info('*   Removing source deb http://www.cs.wisc.edu/condor/debian/development lenny contrib')
        node.ssh.execute('sed -i "s/deb http:\/\/www.cs.wisc.edu\/condor\/debian\/development lenny contrib/#deb http:\/\/www.cs.wisc.edu\/condor\/debian\/development lenny contrib/g" /etc/apt/sources.list')

        log.info('*   Adding SciDB directory "{}"'.format(self.directory))
        self._add_directory(node, self.directory)

        log.info('2.1 Installing packages')
        node.apt_install(' '.join(REQUIRED_PACKAGES))

        log.info('2.2 Configure and start the SSH server')
        node.ssh.execute('sudo service ssh restart')

    def run(self, nodes, master, user, user_shell, volumes):
        super(SciDBInstaller, self).run(nodes, master, user, user_shell, volumes)

        dns_names = ' '.join(map(lambda node: node.dns_name, nodes))

        log.info('Beginning SciDB cluster configuration')

        [self.pool.simple_job(self._set_up_node, (node), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))

        log.info('*   Adding SciDB user "{}"'.format(self.username))
        self._add_user(master, nodes)

        log.info('3   Cloning repository {}'.format(self.repository))
        master.ssh.execute('cd {} && su scidb -c "git clone {} {} {}"'.format(
            self.directory, self.repository, self.directory, 
            '--branch {}'.format(self.branch) if self.branch else ''))
 
        # I guess the Paradigm4 source for Ubuntu 12.04 now requres HTTPS?
        log.info('*   Fixing register_3rdparty_scidb_repository.sh')
        master.ssh.execute('sed -i "s/http:\/\/downloads.paradigm4.com/https:\/\/downloads.paradigm4.com/g" {}/deployment/common/register_3rdparty_scidb_repository.sh'.format(self.directory))

        log.info('4.1 Configure passwordless SSH to all the cluster nodes')
        #self._execute(master, 'echo {password} | deployment/deploy.sh access root "" "" {}'.format(dns_names, password=self.password))
        self._execute(master, 'echo {password} | su scidb deployment/deploy.sh access scidb "" "" {}'.format(dns_names, password=self.password))

        log.info('4.2 N/A')

        log.info('4.3 Toolchain')
        self._execute(master, 'deployment/deploy.sh prepare_toolchain {}'.format(master.dns_name))

        log.info('4.4 Coordinator')
        self._add_swapfile(master)
        self._execute(master, 'deployment/deploy.sh prepare_coordinator {}'.format(master.dns_name))

        log.info('End SciDB node configuration')

        log.info('4.5 N/A')
        log.info('4.6 N/A')

        log.info('5.1 Install Postgres')
        self._execute(master, 'deployment/deploy.sh prepare_postgresql postgres postgres {} {}'.format(
                 self.clients, master.dns_name))

        log.info('5.2 Enable the postgres user to access scidb source code')
        master.ssh.execute('sudo usermod -G scidb -a postgres')
        master.ssh.execute('chmod -R g+rx {}'.format(self.directory))

        log.info('6.1 Environment Variables')
        self._add_environment(master, '/root/.bashrc')
        self._add_environment(master, '/home/scidb/.bashrc'.format(self.directory))

        log.info('6.2 Build')
        #TODO can probably remove now that we've committed revision
        self._ensure_revision(master)
        self._execute(master, 'su scidb -c "./run.py setup -f"')
        self._execute(master, 'su scidb -c "./run.py make -j{}"'.format(self.build_threads))

        log.info('6.3 Local Development')
        self._execute(master, './run.py install -f')

        log.info('6.4 Cluster Development: skipping due to make_packages bug')
        log.info('*   Skipping due to make_packages bug :(')
        #self._execute(master, 'su scidb -c "./run.py make_packages /tmp/packages"')
        #self._execute(master, 'deployment/deploy.sh scidb_install /tmp/packages {}'.format(dns_names))

        log.info('7   Start SciDB')
        self._execute(master, 'stage/install/bin/scidb.py startall mydb')

        log.info('A   Install Shim')
        self._execute(master, 'wget {}'.format(self.shim_uri))
        self._execute(master, 'ldconfig {}/stage/install/lib'.format(self.directory))        
        self._execute(master, 'gdebi --n shim*.deb')
        
        log.info('End SciDB cluster configuration')

    def _add_user(self, master, nodes):
        uid, gid = self._get_new_user_id(self.username)
        map(lambda node: self.pool.simple_job(self.__add_user_to_node, (uid, gid, node), jobid=node.alias), nodes)
        self.pool.wait(numtasks=len(nodes))        
        #self._setup_cluster_user(self.username)
        master.generate_key_for_user(self.username, auth_new_key=True, auth_conn_key=True)
        master.add_to_known_hosts(self.username, nodes)

    def __add_user_to_node(self, uid, gid, node):
        node.add_user(self.username, uid, gid, '/bin/bash')
        node.ssh.execute('echo -e "{username}:{password}" | chpasswd'.format(
            username=self.username, password=self.password))

    def _add_directory(self, node, path):
        node.ssh.execute('mkdir {}'.format(path))
        node.ssh.execute('chown {username} {path}'.format(username=self.username, path=path))
        node.ssh.execute('chgrp {username} {path}'.format(username=self.username, path=path))

    def _add_swapfile(self, node):
        node.ssh.execute('sudo dd if=/dev/zero of=/var/swapfile bs=1024 count=2048k')
        node.ssh.execute('sudo mkswap /var/swapfile')
        node.ssh.execute('sudo swapon /var/swapfile')

    def _add_environment(self, node, path):
        with node.ssh.remote_file(path, 'a') as descriptor:
            descriptor.write('export SCIDB_VER={}\n'.format(SCIDB_VERSION))
            #descriptor.write('export SCIDB_INSTALL_PATH={}\n'.format(SCIDB_INSTALL_PATH))
            #descriptor.write('export PATH=$SCIDB_INSTALL_PATH/bin:$PATH\n')
            descriptor.write('export PATH={}/stage/install/bin:$PATH\n'.format(self.directory))
            descriptor.write('export LD_LIBRARY_PATH={}/stage/install/lib:$LD_LIBRARY_PATH\n'.format(self.directory))
            descriptor.write('export SCIDB_BUILD_TYPE={}\n'.format(self.build_type))

    def _ensure_revision(self, node):
        with node.ssh.remote_file(os.path.join(self.directory, 'revision'), 'w') as descriptor:
            descriptor.write(str(SCIDB_REVISION))

    def _execute(self, node, command):
        node.ssh.execute('cd {} && {}'.format(self.directory, command))