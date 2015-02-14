import os
import time
import random
import string
from starcluster.clustersetup import DefaultClusterSetup
from starcluster.logger import log

SCIDB_VERSION = 14.8
SCIDB_REVISION = 8628
POSTGRES_VERSION = '9.1'
#SCIDB_INSTALL_PATH = '/opt/scidb/$SCIDB_VER'

DEFAULT_USERNAME = 'scidb'
DEFAULT_REPOSITORY = 'https://github.com/BrandonHaynes/scidb.git'
DEFAULT_BRANCH = None
DEFAULT_SHIM_PACKAGE_URI = 'https://paradigm4.github.io/shim/shim_14.8_amd64.deb'
DEFAULT_DIRECTORY = '/mnt/scidb'
DEFAULT_CLIENTS = '0.0.0.0/0'
DEFAULT_BUILD_TYPE = 'RelWithDebInfo'
DEFAULT_BUILD_THREADS = 4

DEFAULT_REDUNDANCY = 1
DEFAULT_INSTANCES_PER_NODE = 1

# http://www.scidb.org/forum/viewtopic.php?f=11&t=530
# Documentation specified Postgres 8.4; I moved to 9.1
REQUIRED_PACKAGES = ['build-essential', 'cmake', 'libboost1.48-all-dev', 
                     'postgresql-9.1', 'libpqxx-3.1', 'libpqxx3-dev', 
                     'libprotobuf7', 'libprotobuf-dev', 'protobuf-compiler', 
                     'doxygen', 'flex', 'bison', 'libxerces-c-dev', 
                     'libxerces-c3.1', 'liblog4cxx10', 'liblog4cxx10-dev', 
                     'libcppunit-1.12-1', 'libcppunit-dev', 'libbz2-dev', 
                     'postgresql-contrib-9.1', 'libconfig++8', 
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
                 build_threads=DEFAULT_BUILD_THREADS,
                 redundancy=DEFAULT_REDUNDANCY,
                 instances_per_node=DEFAULT_INSTANCES_PER_NODE):
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
        self.redundancy = redundancy
        self.instances_per_node = instances_per_node

    def _set_up_node(self, master, node):
        log.info("1   Begin configuration {}".format(node.alias))

        log.info('*   Removing source deb http://www.cs.wisc.edu/condor/debian/development lenny contrib')
        node.ssh.execute('sed -i "s/deb http:\/\/www.cs.wisc.edu\/condor\/debian\/development lenny contrib/#deb http:\/\/www.cs.wisc.edu\/condor\/debian\/development lenny contrib/g" /etc/apt/sources.list')

        log.info('*   Adding SciDB directory "{}"'.format(self.directory))
        self._add_directory(node, self.directory)
        time.sleep(30)

        log.info('*   Add swap file on node {}'.format(node.alias))
        self._add_swapfile(node)

        log.info('*   Setting home directory owner to scidb on node {}'.format(node.alias))
        node.ssh.execute('chown -R scidb /home/scidb')
        node.ssh.execute('chmod 700 /home/scidb/.ssh')
        #log.info('*   Cleaning up scidb user on nodesEnsuring passwordless SSH for node "{}"'.format(node.alias))
        #node.ssh.execute("su scidb -c 'ssh -o StrictHostKeyChecking=no {} ls'".format(master.alias))

        log.info('2.1 Installing packages')
        node.apt_install(' '.join(REQUIRED_PACKAGES))

        log.info('2.2 Configure and start the SSH server')
        node.ssh.execute('sudo service ssh restart')

    def run(self, nodes, master, user, user_shell, volumes):
        super(SciDBInstaller, self).run(nodes, master, user, user_shell, volumes)

        aliases = ' '.join(map(lambda node: node.alias, nodes))

        log.info('Beginning SciDB cluster configuration')

        log.info('*   Adding SciDB user "{}"'.format(self.username))
        self._add_user(master, nodes)
        time.sleep(90)

        [self.pool.simple_job(self._set_up_node, (master, node), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))

        log.info('3   Cloning repository {}'.format(self.repository))
        master.ssh.execute('cd {} && su scidb -c "git clone {} {} {}"'.format(
            self.directory, self.repository, self.directory, 
            '--branch {}'.format(self.branch) if self.branch else ''))
 
        # I guess the Paradigm4 source for Ubuntu 12.04 now requres HTTPS?
        log.info('*   Fixing register_3rdparty_scidb_repository.sh')
        master.ssh.execute('sed -i "s/http:\/\/downloads.paradigm4.com/https:\/\/downloads.paradigm4.com/g" {}/deployment/common/register_3rdparty_scidb_repository.sh'.format(self.directory))

        #log.info('4.1 Configure passwordless SSH to all the cluster nodes')
        #self._execute(master, '''su scidb -c "deployment/deploy.sh access scidb '{password}' '' {}"'''.format(aliases, password=self.password))

        log.info('4.2 N/A')

        log.info('4.3 Toolchain')
        self._execute(master, 'deployment/deploy.sh prepare_toolchain {}'.format(master.alias))

        log.info('4.4 Coordinator')
        self._execute(master, 'deployment/deploy.sh prepare_coordinator {}'.format(master.alias))

        log.info('End SciDB node configuration')

        log.info('4.5 N/A')
        log.info('4.6 N/A')

        log.info('5.1 Install Postgres')
        self._execute(master, 'deployment/deploy.sh prepare_postgresql postgres postgres {} {}'.format(
                 self.clients, master.alias))

        log.info('5.2 Enable the postgres user to access scidb source code')
        master.ssh.execute('sudo usermod -G scidb -a postgres')
        master.ssh.execute('chmod -R g+rx {}'.format(self.directory))

        log.info('6.1 Environment Variables')
        self._add_environment(master, '/root/.bashrc')
        self._add_environment(master, '/home/scidb/.bashrc')

        log.info('6.2 Build')
        #TODO can probably remove now that we've committed revision
        self._ensure_revision(master)
        log.info('    * Setup')
        self._execute(master, 'su scidb -c "./run.py setup -f"')
        log.info('    * Build')
        self._execute(master, 'su scidb -c "./run.py make -j{}"'.format(self.build_threads))

        log.info('6.3 N/A') # Local Development')
        #self._execute(master, './run.py install -f')

        log.info('6.4 Cluster Development')

        log.info('    * Package')
        self._execute(master, 'su scidb -c "./run.py make_packages /tmp/packages -f"')

        log.info('    * Distribute Libraries')
        [self.pool.simple_job(self._distribute_libraries, (master, node), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))

        log.info('    * Install')
        self._execute(master, 'deployment/deploy.sh scidb_install /tmp/packages {}'.format(aliases))

        log.info('    * Redistribute Deployment')
        [self.pool.simple_job(self._copy_deployment, (master, node), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))

        log.info('    * Tweak Root SSH Configuration')
        self._set_root_ssh_config(master)
        log.info('    * Tweak Root SSH Permissions')
        master.ssh.execute('chmod 700 /root/.ssh')
        master.ssh.execute('chmod 600 /root/.ssh/*')
        master.ssh.execute('''sed -i "s/scidb_prepare_node \\"/ssh root@\$\{{hostname\}} 'chmod 600 \/root\/.ssh\/\* \/home\/scidb\/.ssh\/*' \&\& scidb_prepare_node \\"/" {}/deployment/deploy.sh'''.format(self.directory))

        time.sleep(30)

        log.info('*   Set Postgres Listener')
        [self.pool.simple_job(self._set_postgres_listener, (node, '*'), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))
        [self.pool.simple_job(self._add_host_authentication, (node, 'host all all 0.0.0.0/0 md5'), jobid=node.alias) for node in nodes]
        self.pool.wait(len(nodes))

        log.info('    * Prepare')
        log.info('deployment/deploy.sh scidb_prepare scidb "{password}" mydb mydb mydb {directory}/db {instances} default {redundancy} {master_alias} {aliases}'.format(
                instances=self.instances_per_node,
                redundancy=self.redundancy,
                password=self.password,
                directory=self.directory,
                master_alias=master.alias,
                aliases=aliases))
        self._execute(master, 'deployment/deploy.sh scidb_prepare scidb "{password}" mydb mydb mydb {directory}/db {instances} default {redundancy} {master_alias} {aliases}'.format(
                instances=self.instances_per_node,
                redundancy=self.redundancy,
                password=self.password,
                directory=self.directory,
                master_alias=master.alias,
                aliases=aliases))

        log.info('7   Start SciDB')
        log.info('    * Initialize Catalogs')
        self._execute(master, '/opt/scidb/14.8/bin/scidb.py initall mydb -f')
        log.info('    * Start All')
        self._execute(master, '/opt/scidb/14.8/bin/scidb.py startall mydb')

        log.info('A   Install Shim')
        self._execute(master, 'wget {}'.format(self.shim_uri))
        self._execute(master, 'ldconfig {}/stage/install/lib'.format(self.directory))        
        self._execute(master, 'gdebi --n shim*.deb')
        #TODO set shim temporary directory to /mnt/tmp in /var/lib/shim/conf

        log.info('B   Install SciDB-Py')
        master.ssh.execute('pip install requests')
        master.ssh.execute('pip install --upgrade scidb-py')

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
        node.ssh.execute('sudo dd if=/dev/zero of=/mnt/swapfile bs=1024 count=2048k')
        node.ssh.execute('sudo mkswap /mnt/swapfile')
        node.ssh.execute('sudo swapon /mnt/swapfile')

    def _add_environment(self, node, path):
        log.info('TODO {}'.format(path))

        with node.ssh.remote_file(path, 'a') as descriptor:
            descriptor.write('export SCIDB_VER={}\n'.format(SCIDB_VERSION))
            #descriptor.write('export SCIDB_INSTALL_PATH={}\n'.format(SCIDB_INSTALL_PATH))
            #descriptor.write('export PATH=$SCIDB_INSTALL_PATH/bin:$PATH\n')
            descriptor.write('export PATH={}/stage/install/bin:$PATH\n'.format(self.directory))
            descriptor.write('export LD_LIBRARY_PATH={}/stage/install/lib:$LD_LIBRARY_PATH\n'.format(self.directory))
            descriptor.write('export SCIDB_BUILD_TYPE={}\n'.format(self.build_type))

    def _ensure_revision(self, node):
        self._execute(node, 'mv .git temp.git') #TODO
        with node.ssh.remote_file(os.path.join(self.directory, 'revision'), 'w') as descriptor:
            descriptor.write(str(SCIDB_REVISION))

    def _distribute_libraries(self, master, node):
        # Awesome!  SciDB has hardcoded paths (/opt/scidb/*)
        node.ssh.execute('mkdir -p /opt/scidb/{}'.format(SCIDB_VERSION))
        master.ssh.execute('scp -r {directory}/stage/build/debian/scidb-{version}-plugins{directory}/stage/install/* {alias}:/opt/scidb/{version}'.format(
            directory=self.directory, 
            alias=node.alias, 
            version=SCIDB_VERSION))

    def _copy_deployment(self, master, node):
        master.ssh.execute('scp -r {}/stage/install/* {}:/opt/scidb/{}'.format(self.directory, node.alias, SCIDB_VERSION))

    def _set_root_ssh_config(self, node, path='/root/.ssh/config'):
        with node.ssh.remote_file(path, 'w') as descriptor:
            descriptor.write('Host *\n'
                             '   StrictHostKeyChecking no\n'
                             '   UserKnownHostsFile=/dev/null\n'
                             '   IdentityFile ~/.ssh/id_rsa\n'
                             '   User root\n'
                             '\n'
                             'Host *\n'
                             '   StrictHostKeyChecking no\n'
                             '   UserKnownHostsFile=/dev/null\n'
                             '   IdentityFile /home/scidb/.ssh/id_rsa\n'
                             '   User scidb\n')
        node.ssh.execute('chmod 600 {}'.format(path))

    def _set_postgres_listener(self, node, listeners, path='/etc/postgresql/{version}/main/postgresql.conf', version=POSTGRES_VERSION):
        node.ssh.execute(r'sed -i "s/^\s*\#\?\s*listen_addresses\s*=\s*''.*\?''/listen_addresses = \'{listeners}\'/ig" {path}'.format(
            listeners=listeners,
            path=path.format(version=version)))
        node.ssh.execute('sudo service postgresql restart')

    def _add_host_authentication(self, node, authentication, path='/etc/postgresql/{version}/main/pg_hba.conf', version=POSTGRES_VERSION):
        with node.ssh.remote_file(path.format(version=version), 'a') as descriptor:
            descriptor.write(authentication + '\n')
        node.ssh.execute('sudo service postgresql restart')

    def _execute(self, node, command):
        node.ssh.execute('cd {} && {}'.format(self.directory, command))
