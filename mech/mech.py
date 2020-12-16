# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2017 Kevin Chung
# Copyright (c) 2018 German Mendez Bravo (Kronuz)
# Copyright (c) 2020 Mike Kinney
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
'''Mech cli functionality.'''
import logging
import os
import platform
import shutil
import sys


import click

from . import utils
from .mech_instance import MechInstance
from .vmrun import VMrun
from .vbm import VBoxManage
from .__init__ import __version__

LOGGER = logging.getLogger('mech')


class MechAliasedGroup(click.Group):
    '''Enable click command aliases.'''

    def get_command(self, ctx, cmd_name):
        '''get the alias command'''
        try:
            cmd_name = MECH_ALIASES[cmd_name].name
        except KeyError:
            pass
        return super().get_command(ctx, cmd_name)


@click.group(context_settings=utils.context_settings(), cls=MechAliasedGroup)
@click.option('--debug', is_flag=True, default=False)
@click.option('--cloud')
@click.version_option(version=__version__, message='%(prog)s v%(version)s')
@click.pass_context
def cli(ctx, debug, cloud):
    '''Mech is a command line utility for virtual machine automation.

    Create, start, stop, destroy virtual machines (aka instances) with ease.

    VMware Fusion, VMware Workstation, and/or Oracle VirtualBox can be used.

    Mech is similar to Hashicorp's vagrant utility.
    '''
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(filename)s:%(lineno)s %(funcName)s() '
                                  '%(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if debug:
        click.echo('Debug is on')
        LOGGER.setLevel(logging.DEBUG)
        LOGGER.debug('cloud:%s', cloud)

    # ensure that ctx.obj exists and is a dict
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug
    ctx.obj['cloud_name'] = cloud


@cli.command()
@click.option('--detail', '-d', is_flag=True, help='Print detailed info.')
@click.argument('instance', required=False)
@click.pass_context
def list(ctx, detail, instance):
    '''Lists all available instances (using Mechfile)'''

    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('detail:%s cloud_name:%s', detail, cloud_name)

    if cloud_name:
        utils.cloud_run(cloud_name, ['list', 'ls'])
        return

    if detail:
        click.echo('Instance Details')
        click.echo()
    else:
        click.echo('{}\t{}\t{}\t{}\t{}\t{}'.format(
            'NAME'.rjust(20),
            'ADDRESS'.rjust(15),
            'BOX'.rjust(35),
            'VERSION'.rjust(12),
            'PROVIDER'.rjust(12),
            'STATE'.rjust(12),
        ))

    if instance:
        instances = [instance]
    else:
        instances = utils.instances()

    LOGGER.debug('instances:%s', instances)
    mechfiles = utils.load_mechfile()
    LOGGER.debug('mechfiles:%s', mechfiles)
    for name in instances:
        LOGGER.debug('name:%s', name)
        inst = MechInstance(name, mechfiles)
        vm_state = 'unknown'
        if inst.created:
            ip_address = inst.get_ip()
            vm_state = inst.get_vm_state()
            if vm_state is None:
                vm_state = 'unknown'
            if ip_address is None:
                ip_address = 'poweroff'
            elif not ip_address:
                ip_address = 'running'
        else:
            ip_address = 'notcreated'
            vm_state = 'notcreated'

        if detail:
            click.echo('==================================')
            click.echo('From Mechfile:')
            click.echo(inst)
            click.echo()
            if inst.provider == 'virtualbox':
                if inst.created:
                    click.echo('From virtualbox:')
                    click.echo(inst.get_vm_info())
        else:
            # deal with box_version being none
            box_version = inst.box_version
            if inst.box_version is None:
                box_version = ''
            click.echo('{}\t{}\t{}\t{}\t{}\t{}'.format(
                name.rjust(20),
                ip_address.rjust(15),
                inst.box.rjust(35),
                box_version.rjust(12),
                inst.provider.rjust(12),
                vm_state.rjust(12),
            ))


@cli.command()
@click.pass_context
def support(ctx):
    '''Show support info.'''

    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s', cloud_name)

    if cloud_name:
        utils.cloud_run(cloud_name, ['support'])
        return

    click.echo('If you are having issues with mikemech or wish to make feature requests, ')
    click.echo('please check out the GitHub issues at https://github.com/mkinney/mech/issues .')
    click.echo('')
    click.echo('When adding an issue, be sure to include the following:')
    click.echo(' System: {0}'.format(platform.system()))
    click.echo('   Platform: {0}'.format(platform.platform()))
    click.echo('   Release: {0}'.format(platform.uname().release))
    click.echo('   Machine: {0}'.format(platform.uname().machine))
    click.echo(' mikemech: v{0}'.format(__version__))
    click.echo(' Executable: {0}'.format(sys.argv[0]))
    click.echo(' Python: {0} ({1}, {2})'.format(
        platform.python_version(),
        platform.python_implementation(),
        platform.python_compiler(),
    ))


@cli.command()
@click.argument('instance', required=False)
@click.pass_context
def port(ctx, instance):
    '''Displays guest port mappings.'''

    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['port'])
        return

    if platform.system() == 'Linux':
        sys.exit(click.style('This command is not supported on this OS.', fg='red'))

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    # FUTURE: implement port forwarding?
    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.provider == 'vmware':
            click.echo('Instance ({}):'. format(an_instance))
            nat_found = False
            vmrun = VMrun(inst.vmx)
            for line in vmrun.list_host_networks().split('\n'):
                network = line.split()
                if len(network) > 2 and network[2] == 'nat':
                    click.echo(vmrun.list_port_forwardings(network[1]))
                    nat_found = True
            if not nat_found:
                click.secho('Cannot find a nat network', fg='red')
        else:
            click.secho('Not yet implemented on this platform.', fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.option('-s', '--show-only', is_flag=True, default=False)
@click.pass_context
def provision(ctx, instance, show_only):
    '''
    Provision the instance(s).

    Notes:

    Provision types are: 'file', 'shell' (Bash), 'ps' (Powershell), and 'pyinfra'.

    'shell' or 'ps' can be inline.

    'shell', 'ps', and 'pyinfra' can have a remote endpoint ('http', 'https', 'ftp') for the script.
    (ex: 'http://example.com/somefile.sh' or ex: 'ftp://foo.com/install.sh')

    'pyinfra' scripts must end with '.py' and 'pyinfra' must be installed.
    See https://pyinfra.readthedocs.io/en/latest/ for more info.

    Provisioning is run when the instance is started or you can re-run the provisioning.

    An example of provisioning could be installing puppet (or your config tool of choice)
    or preparing the instance "just the way you want it".

    '''

    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s show_only:%s instance:%s', cloud_name, show_only, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['provision'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.created:
            utils.provision(inst, show_only)
        else:
            click.echo('VM not created.')


@cli.command()
@click.argument('instance', required=True)
@click.pass_context
def ip(ctx, instance):
    '''
    Outputs the IP address of the instance.
    '''

    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['ip', 'ip_address'])
        return

    inst = MechInstance(instance)

    if inst.created:
        ip_address = inst.get_ip()
        if ip_address:
            click.secho(ip_address, fg='green')
        else:
            click.secho('Unknown IP address', fg='red')
    else:
        click.secho('VM not created', fg='yellow')


@cli.command()
@click.argument('src', required=True)
@click.argument('dst', required=True)
@click.argument('extra-ssh-args', required=False)
@click.pass_context
def scp(ctx, src, dst, extra_ssh_args):
    '''
    Copies files to and from the instance using SCP.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s src:%s dst:%s extra_ssh_args:%s',
                 cloud_name, src, dst, extra_ssh_args)

    if cloud_name:
        utils.cloud_run(cloud_name, ['scp'])
        return

    dst_instance, dst_is_host, dst = dst.partition(':')
    src_instance, src_is_host, src = src.partition(':')

    instance_name = None
    if dst_is_host and src_is_host:
        sys.exit(click.style('Both src and dst are host destinations', fg='red'))
    if dst_is_host:
        instance_name = dst_instance
    else:
        dst = dst_instance
    if src_is_host:
        instance_name = src_instance
    else:
        src = src_instance

    if instance_name is None:
        sys.exit(click.style('Could not determine instance name.', fg='red'))

    inst = MechInstance(instance_name)

    if inst.created:
        _, _, stderr = utils.scp(inst, src, dst, dst_is_host, extra_ssh_args)
        if stderr != '':
            click.echo(stderr)
    else:
        click.secho('VM not created.', fg='red')


@cli.command()
@click.argument('instance', required=True)
@click.option('--command', '-c', required=False, metavar='COMMAND',
              help='Command to run on instance.')
@click.option('--plain', '-p', is_flag=True, default=False,
              help='Plain mode, leaves authentication up to user.')
@click.argument('extra-ssh-args', required=False)
@click.pass_context
def ssh(ctx, instance, command, plain, extra_ssh_args):
    '''
    Connects to an instance via SSH or runs a command (if COMMAND is supplied).
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s command:%s plain:%s extra_ssh_args:%s',
                 cloud_name, instance, command, plain, extra_ssh_args)

    if cloud_name:
        click.secho('Using `ssh` on cloud instance is not supported.', fg='red')
        return

    inst = MechInstance(instance)

    if inst.created:
        return_code, stdout, stderr = utils.ssh(inst, command, plain, extra_ssh_args)
        LOGGER.debug('command:%s return_code:%d stdout:%s stderr:%s',
                     command, return_code, stdout, stderr)
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr)
        sys.exit(return_code)
    else:
        click.echo('VM not created.')


@cli.command()
@click.argument('instance', required=False)
@click.pass_context
def ssh_config(ctx, instance):
    '''
    Output OpenSSH configuration to connect to the instance.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['ssh-config'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)
        if inst.created:
            click.echo(utils.config_ssh_string(inst.config_ssh()))
        else:
            click.secho('VM ({}) is not created.'.format(an_instance), fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.pass_context
def suspend(ctx, instance):
    '''
    Suspends the instance(s).
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['suspend'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.created:
            if inst.provider == 'vmware':
                vmrun = VMrun(inst.vmx)
                if vmrun.suspend() is None:
                    click.secho('Not suspended', fg='red')
                else:
                    click.secho('Suspended', fg='green')
            else:
                click.secho('Not sure equivalent command on this platform.', fg='red')
                click.secho('If you know, please open issue on github.', fg='red')
        else:
            click.secho('VM has not been created.')


@cli.command()
@click.argument('instance', required=False)
@click.option('--disable-shared-folders', is_flag=True, default=False)
@click.pass_context
def resume(ctx, instance, disable_shared_folders):
    '''
    Resume paused/suspended instance(s).
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s disable_shared_folders:%s',
                 cloud_name, instance, disable_shared_folders)

    if cloud_name:
        utils.cloud_run(cloud_name, ['resume', 'unpause'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)
        inst.disable_shared_folders = disable_shared_folders
        LOGGER.debug('instance:%s', instance)

        # if we have started this instance before, try to unpause
        if inst.created:
            utils.unpause_vm(inst)
        else:
            click.secho('VM not created', fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.pass_context
def upgrade(ctx, instance):
    '''
    Upgrade the VM and virtual hardware for the instance(s).

    Note: The VMs must be created and stopped.

    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['upgrade'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.created:
            if inst.provider == 'vmware':
                vmrun = VMrun(inst.vmx)
                state = vmrun.check_tools_state(quiet=True)
                if state == 'running':
                    click.secho('VM must be stopped before doing upgrade.')
                else:
                    if vmrun.upgradevm(quiet=False) is None:
                        click.secho('Not upgraded', fg='red')
                    else:
                        click.secho('Upgraded', fg='yellow')
            else:
                click.secho('Functionality not available on this platform.', fg='red')
        else:
            click.secho('VM ({}) not created.'.format(an_instance), fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.pass_context
def pause(ctx, instance):
    '''
    Pauses the instance(s).
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['pause'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.created:
            if inst.provider == 'vmware':
                vmrun = VMrun(inst.vmx)
                pause_results = vmrun.pause()
                if pause_results is None:
                    click.secho('Not paused', fg='red')
                else:
                    click.secho('Paused', fg='yellow')
            else:
                vbm = VBoxManage()
                pause_results = vbm.pause(inst.name)
                if pause_results is None:
                    click.secho('Not paused', fg='red')
                else:
                    click.secho('Paused', fg='yellow')
        else:
            click.secho('VM ({}) not created.'.format(an_instance), fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.option('--force', '-f', is_flag=True, default=False, help='Force a hard stop.')
@click.pass_context
def down(ctx, instance, force):
    '''
    Stops the instance(s).
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s force:%s', cloud_name, instance, force)

    if cloud_name:
        utils.cloud_run(cloud_name, ['down', 'halt', 'stop'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if inst.created:
            if inst.provider == 'vmware':
                vmrun = VMrun(inst.vmx)
                if not force and vmrun.installed_tools():
                    stopped = vmrun.stop()
                else:
                    stopped = vmrun.stop(mode='hard')
                if stopped is None:
                    click.secho('Not stopped', fg='red')
                else:
                    click.secho('Stopped', fg='green')
            else:
                vbm = VBoxManage()
                stopped = vbm.stop(vmname=inst.name, quiet=True)
                if stopped is None:
                    click.secho('Not stopped', fg='red')
                else:
                    click.secho('Stopped', fg='green')
        else:
            click.secho('VM ({}) not created.'.format(an_instance), fg='red')


@cli.command()
@click.argument('instance', required=False)
@click.option('-f', '--force', is_flag=True, default=False, help='Destroy without confirmation.')
@click.pass_context
def destroy(ctx, instance, force):
    '''
    Stops and deletes all traces of the instances.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s force:%s', cloud_name, instance, force)

    if cloud_name:
        utils.cloud_run(cloud_name, ['destroy'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        if os.path.exists(inst.path):
            if force or utils.confirm('Are you sure you want to delete {} '
                                      'at {}'.format(inst.name, inst.path), default='n'):
                click.secho('Deleting ({})...'.format(an_instance), fg='green')

                if inst.provider == 'vmware':
                    vmrun = VMrun(inst.vmx)
                    vmrun.stop(mode='hard', quiet=True)
                    vmrun.delete_vm()
                else:
                    vbm = VBoxManage()
                    vbm.stop(vmname=inst.name, quiet=True)
                    vbm.unregister(vmname=inst.name, quiet=True)

                if os.path.exists(inst.path):
                    shutil.rmtree(inst.path)
                click.echo('Deleted')
            else:
                click.secho('Delete aborted.', fg='red')
        else:
            click.secho('VM ({}) not created.'.format(an_instance), fg='red')


@cli.command()
@click.argument('instance', required=True)
@click.pass_context
def ps(ctx, instance):
    '''
    List running processes in Guest OS.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s', cloud_name, instance)

    if cloud_name:
        utils.cloud_run(cloud_name, ['ps', 'process-status', 'process_status'])
        return

    inst = MechInstance(instance)

    if inst.created:
        _, stdout, _ = utils.ssh(inst, 'ps -ef')
        click.echo(stdout)
    else:
        click.echo('VM {} not created.'.format(instance))


@cli.command()
@click.option('--purge', '-p', is_flag=True, default=False, help='Kill and remove any instances.')
@click.pass_context
def global_status(ctx, purge):
    '''
    Outputs info about all instances running on this host and optionally destroy them.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s purge:%s', cloud_name, purge)

    if cloud_name:
        utils.cloud_run(cloud_name, ['global-status', 'global_status', 'gs'])
        return

    if purge:
        utils.cleanup_dir_and_vms_from_dir('', all_vms=True)
    else:
        vmrun = VMrun()
        if vmrun.installed():
            click.echo('===VMware VMs===')
            click.echo(vmrun.list())

        vbm = VBoxManage()
        if vbm.installed():
            click.echo('===VirtualBox VMs===')
            click.echo(vbm.list())


@cli.command()
@click.argument('instance', required=False)
@click.option('--disable-provisioning', is_flag=True, default=False, help='Do not provision.')
@click.option('--disable-shared-folders', is_flag=True, default=False, help='Do not share folders.')
@click.option('--gui', is_flag=True, default=False, help='Start GUI, otherwise starts headless.')
@click.option('--memsize', metavar='MEMORY', help='Specify memory size in MB.')
@click.option('--no-cache', is_flag=True, default=False, help='Do not save the downloaded box.')
@click.option('--no-nat', is_flag=True, default=False,
              help='Do not use NAT networking (i.e., use bridged).')
@click.option('--numvcpus', metavar='VCPUS', help='Specify number of vcpus.')
@click.option('--add-custom-interface', metavar='VMNET', help='Add a custom netowrk interface (i.e., 3 for VMnet3)')
@click.option('-r', '--remove-vagrant', is_flag=True, default=False, help='Remove vagrant user.')
@click.pass_context
def up(ctx, instance, disable_provisioning, disable_shared_folders, gui, memsize, no_cache,
       no_nat, numvcpus, add_custom_interface, remove_vagrant):
    '''
    Starts and provisions instance(s).

    Notes:

    If no instance is specified, all instances will be started.

    The options ('memsize', 'numvcpus', 'add-custom-interface', and 'no-nat') will only be applied
    upon first run of the 'up' command.

    The 'no-nat' option will only be applied if there is no network
    interface supplied in the box file for 'vmware'. For 'virtualbox',
    if you need internet access from the vm, then you will want to
    use 'no-nat'. Interface 'en0' will be used for bridge.

    Unless 'disable-shared-folders' is used, a default read/write
    share called 'mech' will be mounted from the current directory.
    '/mnt/hgfs/mech' on 'vmware' and '/mnt/mech' on 'virtualbox'
    To add/change shared folders, modify the Mechfile directly, then
    stop/start the VM.

    The 'remove-vagrant' option will remove the vagrant account from the
    guest VM which is what 'mech' uses to communicate with the VM.
    Be sure you can connect/admin the instance before using this option.
    Be sure to check that root cannot ssh, or change the root password.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s instance:%s disable_provisioning:%s disable_shared_folders:%s '
                 'gui:%s memsize:%s no_cache:%s no_nat:%s numvcpus:%s remove_vagrant:%s',
                 cloud_name, instance, disable_provisioning, disable_shared_folders,
                 gui, memsize, no_cache, no_nat, numvcpus, add_custom_interface, remove_vagrant)

    if cloud_name:
        utils.cloud_run(cloud_name, ['up', 'start'])
        return

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    for an_instance in instances:
        inst = MechInstance(an_instance)

        inst.gui = gui
        inst.disable_shared_folders = disable_shared_folders
        inst.disable_provisioning = disable_provisioning
        inst.remove_vagrant = remove_vagrant
        inst.no_nat = no_nat

        if not utils.report_provider(inst.provider):
            return

        location = inst.url
        if not location:
            location = inst.box_file

        # only run init_box on first 'up'
        # extracts the VM files from the singular .box archive
        if not inst.created:
            path_to_vmx_or_vbox = utils.init_box(
                an_instance,
                box=inst.box,
                box_version=inst.box_version,
                location=location,
                instance_path=inst.path,
                save=not no_cache,
                numvcpus=numvcpus,
                add_custom_interface = add_custom_interface,
                memsize=memsize,
                no_nat=no_nat,
                windows=inst.windows,
                provider=inst.provider)
            if inst.provider == 'vmware':
                inst.vmx = path_to_vmx_or_vbox
            else:
                inst.vbox = path_to_vmx_or_vbox
                vbm = VBoxManage()
                if memsize:
                    vbm.memory(inst.name, memsize)
                if numvcpus:
                    vbm.cpus(inst.name, numvcpus)
                # virtualbox wants to add shared folder before starting VM
                utils.share_folders(inst)

            inst.created = True

        utils.start_vm(inst)


@cli.command()
@click.argument('name', required=True)
@click.pass_context
def remove(ctx, name):
    '''
    Remove instance from the Mechfile.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s name:%s', cloud_name, name)

    if cloud_name:
        utils.cloud_run(cloud_name, ['remove', 'delete', 'rm'])
        return

    mechfiles = utils.load_mechfile()
    LOGGER.debug('mechfiles:%s', mechfiles)

    inst = mechfiles.get(name, None)
    if inst:
        click.secho('Removing ({}) from the Mechfile.'.format(name), fg='green')
        utils.remove_mechfile_entry(name=name)
        click.secho('Removed from the Mechfile.', fg='green')
    else:
        sys.exit(click.style('There is no instance called '
                             '({}) in the Mechfile.'.format(name), fg='red'))


@cli.command()
@click.argument('name', required=True)
@click.argument('location', required=True)
@click.option('--add-me', '-a', is_flag=True, default=False,
              help='Add the current user/pubkey to guest.')
@click.option('--box', metavar='BOXNAME', help='Name of the box (ex: bento/ubuntu-10.04).')
@click.option('--box-version', metavar='VERSION', help='Constrain to specific box version.')
@click.option('--provider', metavar='PROVIDER', default='vmware',
              help='Provider (`vmware` or `virtualbox`)')
@click.option('--use-me', '-u', is_flag=True, default=False,
              help='Use the current user for mech interactions.')
@click.option('--windows', '-w', is_flag=True, default=False, help='Windows instance')
@click.pass_context
def add(ctx, name, location, add_me, box, box_version, provider, use_me, windows):
    '''
    Add instance to the Mechfile.

    Notes:

    The 'add-me' option will add the currently logged in user to the guest,
    add the same user to sudoers, and add the id_rsa.pub key to the authorized_hosts file
    for that user.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s name:%s location:%s add_me:%s box:%s box_version:%s '
                 'provider:%s use_me:%s windows:%s', cloud_name, name, location, add_me, box,
                 box_version, provider, use_me, windows)

    if cloud_name:
        utils.cloud_run(cloud_name, ['add'])
        return

    if not utils.report_provider(provider):
        return

    utils.report_provider(provider)

    click.secho('Adding ({}) to the Mechfile.'.format(name), fg='green')

    utils.add_to_mechfile(
        location=location,
        box=box,
        name=name,
        box_version=box_version,
        add_me=add_me,
        use_me=use_me,
        provider=provider,
        windows=windows)
    click.secho('Added to the Mechfile.', fg='green')


@cli.command()
@click.argument('location', required=True)
@click.option('--add-me', '-a', is_flag=True, default=False,
              help='Add the current user/pubkey to guest.')
@click.option('--box', metavar='BOXNAME', help='Name of the box (ex: bento/ubuntu-10.04).')
@click.option('--box-version', metavar='VERSION', help='Constrain to specific box version.')
@click.option('--force', '-f', is_flag=True, default=False, help='Overwrite existing Mechfile.')
@click.option('--name', metavar='INSTANCE', default='first',
              help='Name of the instance (ex: `first`).')
@click.option('--provider', metavar='PROVIDER', default='vmware',
              help='Provider (`vmware` or `virtualbox`)')
@click.option('--use-me', '-u', is_flag=True, default=False,
              help='Use the current user for mech interactions.')
@click.option('--windows', '-w', is_flag=True, default=False, help='Windows instance')
@click.pass_context
def init(ctx, location, add_me, box, box_version, force, name, provider, use_me, windows):
    '''
    Initialize Mechfile.

    Notes:

    The location can be a:

        + URL (ex: 'http://example.com/foo.box'),

        + box file (ex: 'file:/mnt/boxen/foo.box'),

        + json file (ex: 'file:/tmp/foo.json'), or

        + HashiCorp account/box (ex: 'bento/ubuntu-18.04').

    A default shared folder name 'mech' will be available
    in the guest for the current directory.

    The 'add-me' option will add the currently logged in user to the guest,
    add the same user to sudoers, and add the id_rsa.pub key to the
    authorized_hosts file for that user.

    The 'use-me' option will use the currently logged in user for
    future interactions with the guest instead of the vagrant user.

    The 'windows' flag is used for provisioning. When enabled, winrm will
    be used instead of scp.
    '''
    cloud_name = ctx.obj['cloud_name']
    LOGGER.debug('cloud_name:%s location:%s add_me:%s box:%s box_version:%s '
                 'force:%s name:%s provider:%s use_me:%s windows:%s', cloud_name,
                 location, add_me, box, box_version,
                 force, name, provider, use_me, windows)

    if not utils.valid_provider(provider):
        sys.exit(click.style('Need to provide valid provider.', fg='red'))

    if cloud_name:
        utils.cloud_run(cloud_name, ['init'])
        return

    if os.path.exists('Mechfile') and not force:
        sys.exit(click.style('`Mechfile` already exists in this directory. Remove it \n'
                             'before running `mech init` or use `mech add`.', fg='red'))

    utils.report_provider(provider)

    click.secho('Initializing mech', fg='green')
    utils.init_mechfile(
        location=location,
        box=box,
        name=name,
        box_version=box_version,
        add_me=add_me,
        use_me=use_me,
        provider=provider,
        windows=windows)
    click.secho('A `Mechfile` has been initialized and placed in this directory. \n'
                'You are now ready to `mech up` your first virtual environment!', fg='green')


MECH_ALIASES = {
    'delete': remove,
    'global-status': global_status,
    'gs': global_status,
    'halt': down,
    'ip-address': ip,
    'ip_address': ip,
    'ls': list,
    'process-status': ps,
    'process_status': ps,
    'rm': remove,
    'start': up,
    'stop': down,
    'unpause': resume,
}
