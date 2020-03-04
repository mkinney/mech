import logging
import os
import platform
import shutil
import sys


import click


from . import utils
from .__init__ import __version__
from .mech_instance import MechInstance
from .vmrun import VMrun
from .vbm import VBoxManage

# for short and long help options
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

# TODO: change back to __name__
# LOGGER = logging.getLogger(__name__)
LOGGER = logging.getLogger('mech')


class AliasedGroup(click.Group):
    '''Enable click command aliases.'''
    def get_command(self, ctx, cmd_name):
        '''get the alias command'''
        try:
            cmd_name = ALIASES[cmd_name].name
        except KeyError:
            pass
        return super().get_command(ctx, cmd_name)


@click.group(context_settings=CONTEXT_SETTINGS, cls=AliasedGroup)
@click.option('--debug', is_flag=True, default=False)
@click.option('--cloud')
@click.version_option(version=__version__, message='%(prog)s v%(version)s')
@click.pass_context
def cli(ctx, debug, cloud):
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
        click.echo("{}\t{}\t{}\t{}\t{}\t{}".format(
            'NAME'.rjust(20),
            'ADDRESS'.rjust(15),
            'BOX'.rjust(35),
            'VERSION'.rjust(12),
            'PROVIDER'.rjust(12),
            'STATE'.rjust(12),
        ))

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
        sys.exit(click.style('This command is not supported on this OS.', fg="red"))

    if instance:
        # single instance
        instances = [instance]
    else:
        # multiple instances
        instances = utils.instances()

    # FUTURE: implement port forwarding?
    for instance in instances:
        inst = MechInstance(instance)

        if inst.provider == 'vmware':
            click.echo('Instance ({}):'. format(instance))
            nat_found = False
            vmrun = VMrun(inst.vmx)
            for line in vmrun.list_host_networks().split('\n'):
                network = line.split()
                if len(network) > 2 and network[2] == 'nat':
                    click.echo(vmrun.list_port_forwardings(network[1]))
                    nat_found = True
            if not nat_found:
                click.secho("Cannot find a nat network", fg="red")
        else:
            click.secho("Not yet implemented on this platform.", fg="red")


@cli.command()
@click.argument('instance', required=False)
@click.option('--show-only', is_flag=True, default=False)
@click.pass_context
def provision(ctx, instance, show_only):
    """
    Provision the instance(s).

    Notes:
      - There are a few provision types: 'file', 'shell', and 'pyinfra'.
      - 'shell' can be inline.
      - 'shell' and 'pyinfra' can have a remote endpoint ('http', 'https',
        'ftp') for the script.
        (ex: 'http://example.com/somefile.sh' or ex: 'ftp://foo.com/install.sh')
      - 'pyinfra' scripts must end with '.py' and 'pyinfra' must be installed.
        See https://pyinfra.readthedocs.io/en/latest/ for more info.
      - Provisioning is run when the instance is started. This option
        is if you want to re-run the provisioning.
      - An example of provisioning could be installing puppet (or your config tool
        of choice).

    """

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
            click.echo("VM not created.")


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
@click.option('--plain', is_flag=True, default=False,
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
        rc, stdout, stderr = utils.ssh(inst, command, plain, extra_ssh_args)
        LOGGER.debug('command:%s rc:%d stdout:%s stderr:%s', command, rc, stdout, stderr)
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr)
        sys.exit(rc)
    else:
        click.echo('VM not created.')


@cli.command()
@click.argument('instance', required=True)
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
@click.option('--force', is_flag=True, default=False, help='Force a hard stop.')
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
@click.option('--force', is_flag=True, default=False, help='Destroy without confirmation.')
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
@click.option('--purge', is_flag=True, default=False, help='Kill and remove any instances.')
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


# operation aliases
ALIASES = {
    'ls': list,
    'ip_address': ip,
    'ip-address': ip,
    'unpause': resume,
    'stop': down,
    'halt': down,
    'process-status': ps,
    'process_status': ps,
    'global-status': global_status,
    'gs': global_status,
}
