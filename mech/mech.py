# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import glob
import time
import utils
import shutil
import logging

from clint.textui import colored, puts

from vmrun import VMrun
from command import Command

logger = logging.getLogger(__name__)


HOME = os.path.expanduser("~/.mech")


class MechCommand(Command):
    def get(self, name):
        if not hasattr(self, 'mechfile'):
            self.mechfile = utils.load_mechfile()
        return self.mechfile.get(name)

    @property
    def vmx(self):
        vmx = self.get('vmx')
        if vmx:
            return vmx
        puts(colored.red("Couldn't find a VMX in the mechfile"))
        sys.exit(1)

    @property
    def user(self):
        return self.get('user')


class MechBox(MechCommand):
    """
    Usage: mech box <subcommand> [<args>...]

    Available subcommands:
        add               add a box to the catalog of available boxes
        list              list available boxes in the catalog
        outdated          checks for outdated boxes
        prune             removes old versions of installed boxes
        remove            removes a box that matches the given name
        repackage
        update

    For help on any individual subcommand run `mech box <subcommand> -h`
    """

    def add(self, arguments):
        """
        Add a box to the catalog of available boxes.

        Usage: mech box add [options] <name|url|path>

        Notes:
            The box descriptor can be the name of a box on HashiCorp's Vagrant Cloud,
            or a URL, a local .box or .tar file, or a local .json file containing
            the catalog metadata.

        Options:
            -f, --force                      Overwrite an existing box if it exists
                --insecure                   Do not validate SSL certificates
                --cacert FILE                CA certificate for SSL download
                --capath DIR                 CA certificate directory for SSL download
                --cert FILE                  A client SSL cert, if needed
                --box-version VERSION        Constrain version of the added box
                --checksum CHECKSUM          Checksum for the box
                --checksum-type TYPE         Checksum type (md5, sha1, sha256)
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        url = arguments['<name | url | path>']
        name = arguments['--name']
        version = arguments['--box-version']
        force = arguments['--force']
        requests_kwargs = {}
        if arguments['--insecure']:
            requests_kwargs['verify'] = False
        elif arguments['--capath']:
            requests_kwargs['verify'] = arguments['--capath']
        elif arguments['--cacert']:
            requests_kwargs['verify'] = arguments['--cacert']
        elif arguments['--cert']:
            requests_kwargs['cert'] = arguments['--cert']
        return utils.add_box(url, name=name, version=version, force=force, requests_kwargs=requests_kwargs)

    def list(self, arguments):
        """
        List all available boxes in the catalog.

        Usage: mech box list [options]

        Options:
            -i, --box-info                   Displays additional information about the boxes
            -h, --help                       Print this help
        """
        vms = glob.glob(os.path.join(HOME, 'boxes', '*'))
        for vm in vms:
            puts(os.path.basename(vm))
    ls = list

    def outdated(self, arguments):
        """
        Checks if there is a new version available for the box.

        Usage: mech box outdated [options]

        Options:
                --global                     Check all boxes installed
                --insecure                   Do not validate SSL certificates
                --cacert FILE                CA certificate for SSL download
                --capath DIR                 CA certificate directory for SSL download
                --cert FILE                  A client SSL cert, if needed
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def prune(self, arguments):
        """
        Remove old versions of installed boxes.

        Usage: mech box prune [options]

        Notes:
            If the box is currently in use mech will ask for confirmation.

        Options:
            -n, --dry-run                    Only print the boxes that would be removed.
                --name NAME                  The specific box name to check for outdated versions.
            -f, --force                      Destroy without confirmation even when box is in use.
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def remove(self, arguments):
        """
        Remove a box from mech that matches the given name.

        Usage: mech box remove [options] <name>

        Options:
            -f, --force                      Remove without confirmation.
                --box-version VERSION        The specific version of the box to remove
                --all                        Remove all available versions of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def repackage(self, arguments):
        """
        Repackage the box that is in use in the current mech environment.

        Usage: mech box repackage [options] <name> <version>

        Notes:
            Puts it in the current directory so you can redistribute it.
            The name and version of the box can be retrieved using mech box list.

        Options:
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def update(self, arguments):
        """
        Update the box that is in use in the current mech environment.

        Usage: mech box update [options]

        Notes:
            Only if there any updates available. This does not destroy/recreate
            the machine, so you'll have to do that to see changes.

        Options:
            -f, --force                      Overwrite an existing box if it exists
                --insecure                   Do not validate SSL certificates
                --cacert FILE                CA certificate for SSL download
                --capath DIR                 CA certificate directory for SSL download
                --cert FILE                  A client SSL cert, if needed
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))


class MechSnapshot(MechCommand):
    """
    Usage: mech snapshot <subcommand> [<args>...]

    Available subcommands:
        delete            delete a snapshot taken previously with snapshot save
        list              list all snapshots taken for a machine
        pop               restore state that was pushed with `mech snapshot push`
        push              push a snapshot of the current state of the machine
        restore           restore a snapshot taken previously with snapshot save
        save              take a snapshot of the current state of the machine

    For help on any individual subcommand run `mech snapshot <subcommand> -h`
    """

    def delete(self, arguments):
        """
        Delete a snapshot taken previously with snapshot save.

        Usage: mech snapshot delete [options] <name>

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        name = arguments['<name>']

        vm = VMrun(self.vmx)
        if vm.deleteSnapshot(name) is None:
            puts(colored.red("Cannot delete snapshot"))
        else:
            puts(colored.green("Snapshot {} deleted".format(name)))

    def list(self, arguments):
        """
        List all snapshots taken for a machine.

        Usage: mech snapshot list [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        vm = VMrun(self.vmx)
        puts(vm.listSnapshots())

    def pop(self, arguments):
        """
        Restore state that was pushed with `mech snapshot push`.

        Usage: mech snapshot pop [options]

        Options:
                --provision                  Enable provisioning
                --no-delete                  Don't delete the snapshot after the restore
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def push(self, arguments):
        """
        Push a snapshot of the current state of the machine.

        Usage: mech snapshot push [options]

        Notes:
            Take a snapshot of the current state of the machine and 'push'
            it onto the stack of states. You can use `mech snapshot pop`
            to restore back to this state at any time.

            If you use `mech snapshot save` or restore at any point after
            a push, pop will still bring you back to this pushed state.

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def restore(self, arguments):
        """
        Restore a snapshot taken previously with snapshot save.

        Usage: mech snapshot restore [options] <name>

        Options:
                --provision                  Enable provisioning
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def save(self, arguments):
        """
        Take a snapshot of the current state of the machine.

        Usage: mech snapshot save [options] <name>

        Notes:
            Take a snapshot of the current state of the machine. The snapshot
            can be restored via `mech snapshot restore` at any point in the
            future to get back to this exact machine state.

            Snapshots are useful for experimenting in a machine and being able
            to rollback quickly.

        Options:
            -f  --force                      Replace snapshot without confirmation
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        name = arguments['<name>']

        vm = VMrun(self.vmx)
        if vm.snapshot(name) is None:
            puts(colored.red("Cannot take snapshot"))
        else:
            puts(colored.green("Snapshot {} taken".format(name)))


class Mech(MechCommand):
    """
    Usage: mech [options] <command> [<args>...]

    Options:
        -v, --version                    Print the version and exit.
        -h, --help                       Print this help.
        --debug                          Show debug messages.

    Common commands:
        init              initializes a new mech environment by creating a mechfile
        destroy           stops and deletes all traces of the mech machine
        (up|start)        starts and provisions the mech environment
        (down|stop|halt)  stops the mech machine
        suspend           suspends the machine
        pause             pauses the mech machine
        ssh               connects to machine via SSH
        scp               copies files to and from the machine via SCP
        ip                outputs ip of the mech machine
        box               manages boxes: installation, removal, etc.
        (status|ps)       outputs status mech environments for this user
        provision         provisions the mech machine
        reload            restarts mech machine, loads new mechfile configuration
        resume            resume a paused/suspended mech machine
        snapshot          manages snapshots: saving, restoring, etc.
        port              displays information about guest port mappings
        push              deploys code in this environment to a configured destination

    For help on any individual command run `mech <command> -h`

    Example:

        Initializing and using a machine from HashiCorp's Vagrant Cloud:

            mech init bento/ubuntu-14.04
            mech up
            mech ssh
    """

    subcommand_name = '<command>'

    def __init__(self, arguments):
        super(Mech, self).__init__(arguments)

        logger = logging.getLogger()
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        if arguments['--debug']:
            logger.setLevel(logging.DEBUG)

    box = MechBox
    snapshot = MechSnapshot

    def init(self, arguments):
        """
        Initializes a new mech environment by creating a mechfile.

        Usage: mech init [options] [<name|url|path>]

        Notes:
            The box descriptor can be the name of a box on HashiCorp's Vagrant Cloud,
            or a URL, a local .box or .tar file, or a local .json file containing
            the catalog metadata.

        Options:
            -f, --force                      Overwrite existing mechfile
                --insecure                   Do not validate SSL certificates
                --cacert FILE                CA certificate for SSL download
                --capath DIR                 CA certificate directory for SSL download
                --cert FILE                  A client SSL cert, if needed
                --box-version VERSION        Constrain version of the added box
                --checksum CHECKSUM          Checksum for the box
                --checksum-type TYPE         Checksum type (md5, sha1, sha256)
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        url = arguments['<name | url | path>']
        name = arguments['--name']
        version = arguments['--box-version']
        force = arguments['--force']
        requests_kwargs = {}
        if arguments['--insecure']:
            requests_kwargs['verify'] = False
        elif arguments['--capath']:
            requests_kwargs['verify'] = arguments['--capath']
        elif arguments['--cacert']:
            requests_kwargs['verify'] = arguments['--cacert']
        elif arguments['--cert']:
            requests_kwargs['cert'] = arguments['--cert']

        if os.path.exists('mechfile') and not force:
            puts(colored.red("`mechfile` already exists in this directory."))
            puts(colored.red("Remove it before running `mech init`."))
            return

        puts(colored.green("Initializing mech"))
        box = utils.add_box(url, name=name, version=version, requests_kwargs=requests_kwargs)
        if box:
            utils.init_box(box, url)
            puts(colored.green("Box initialized"))
        else:
            puts(colored.red("Couldn't initialize mech"))

    def status(self, arguments):
        """
        Outputs mech environments status for this user.

        Usage: mech status [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        vm = VMrun()
        puts(vm.list())
    ps = status

    def up(self, arguments):
        """
        Starts and provisions the mech environment.

        Usage: mech up [options]

        Options:
                --gui                        Start GUI
                --provision                  Enable provisioning
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        gui = arguments['--gui']

        vm = VMrun(self.vmx)
        started = vm.start(gui=gui)
        if started is None:
            puts(colored.red("VM not started"))
        else:
            time.sleep(3)
            if vm.installedTools():
                puts(colored.blue("Getting IP address..."))
                ip = vm.getGuestIPAddress()
                puts(colored.blue("Sharing current folder..."))
                vm.enableSharedFolders()
                vm.addSharedFolder('mech', os.getcwd(), quiet=True)
                if started:
                    puts(colored.green("VM started on {}".format(ip)))
                else:
                    puts(colored.yellow("VM already was started on {}".format(ip)))
            else:
                puts(colored.yellow("VMWare Tools is not installed or running..."))
                if started:
                    puts(colored.green("VM started"))
                else:
                    puts(colored.yellow("VM already was started"))
    start = up

    def destroy(self, arguments):
        """
        Stops and deletes all traces of the mech machine.

        Usage: mech destroy [options]

        Options:
            -f, --force                      Destroy without confirmation.
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        force = arguments['--force']

        directory = os.path.dirname(self.vmx)
        name = os.path.basename(directory)
        if force or utils.confirm("Are you sure you want to delete {name} at {directory}".format(name=name, directory=directory), default='n'):
            puts(colored.green("Deleting..."))
            vm = VMrun(self.vmx)
            vm.stop(mode='hard')
            time.sleep(3)
            shutil.rmtree(directory)
        else:
            puts(colored.red("Deletion aborted"))

    def down(self, arguments):
        """
        Stops the mech machine.

        Usage: mech down [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        vm = VMrun(self.vmx)
        if vm.installedTools():
            stopped = vm.stop()
        else:
            stopped = vm.stop(mode='hard')
        if stopped is None:
            puts(colored.red("Not stopped", vm))
        else:
            puts(colored.green("Stopped", vm))
    stop = down
    halt = down

    def pause(self, arguments):
        """
        Pauses the mech machine.

        Usage: mech pause [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        vm = VMrun(self.vmx)
        if vm.pause() is None:
            puts(colored.red("Not paused", vm))
        else:
            puts(colored.yellow("Paused", vm))

    def resume(self, arguments):
        """
        Resume a paused/suspended mech machine.

        Usage: mech resume [options]

        Options:
                --provision                  Enable provisioning
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        vm = VMrun(self.vmx)

        # Try to unpause
        if vm.unpause(quiet=True) is not None:
            time.sleep(1)
            if vm.installedTools():
                puts(colored.blue("Getting IP address..."))
                ip = vm.getGuestIPAddress(wait=False, quiet=True)
                puts(colored.green("VM resumed on {}".format(ip)))

        # Otherwise try starting
        else:
            started = vm.start()
            if started is None:
                puts(colored.red("VM not started"))
            else:
                time.sleep(3)
                if vm.installedTools():
                    puts(colored.blue("Getting IP address..."))
                    ip = vm.getGuestIPAddress()
                    puts(colored.blue("Sharing current folder..."))
                    vm.enableSharedFolders()
                    vm.addSharedFolder('mech', os.getcwd(), quiet=True)
                    if started:
                        puts(colored.green("VM started on {}".format(ip)))
                    else:
                        puts(colored.yellow("VM already was started on {}".format(ip)))
                else:
                    puts(colored.yellow("VMWare Tools is not installed or running..."))
                    if started:
                        puts(colored.green("VM started"))
                    else:
                        puts(colored.yellow("VM already was started"))

    def suspend(self, arguments):
        """
        Suspends the machine.

        Usage: mech suspend [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        vm = VMrun(self.vmx)
        if vm.suspend() is None:
            puts(colored.red("Not suspended", vm))
        else:
            puts(colored.green("Suspended", vm))

    def ssh(self, arguments):
        """
        Connects to machine via SSH.

        Usage: mech ssh [options] [-- <extra ssh args>...]

        Options:
                --user USERNAME
            -c, --command COMMAND            Execute an SSH command directly
            -p, --plain                      Plain mode, leaves authentication up to user
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        if arguments['--plain']:
            authentication = ''
        else:
            user = arguments['--user']
            if user is None:
                user = self.user
            authentication = '{}@'.format(user)
        extra = arguments['<extra ssh args>']
        command = arguments['--command']

        vm = VMrun(self.vmx)
        ip = vm.getGuestIPAddress()
        if ip:
            puts("Connecting to {}".format(colored.green(ip)))
            cmd = 'ssh {}{}'.format(authentication, ip)
            if extra:
                cmd += ' ' + ' '.join(extra)
            if command:
                cmd += ' -- {}'.format(command)
            os.system(cmd)
        else:
            puts(colored.red("IP not found"))

    def scp(self, arguments):
        """
        Copies files to and from the machine via SCP.

        Usage: mech scp [options] <src> <dst> [-- <extra scp args>...]

        Options:
                --user USERNAME
            -p, --plain                      Plain mode, leaves authentication up to user
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        if arguments['--plain']:
            authentication = ''
        else:
            user = arguments['--user']
            if user is None:
                user = self.user
            authentication = '{}@'.format(user)
        extra = arguments['<extra scp args>']
        src = arguments['<src>']
        dst = arguments['<dst>']

        vm = VMrun(self.vmx)
        ip = vm.getGuestIPAddress()
        if ip:
            src_is_host = src.startswith(":")
            dst_is_host = dst.startswith(":")

            if src_is_host and dst_is_host:
                puts(colored.red("Both src and host are host destinations"))
                sys.exit(1)

            if dst_is_host:
                dst = dst[1:]
                puts("Sending {src} to {authentication}{ip}:{dst}".format(
                    authentication=colored.green(authentication),
                    ip=colored.green(ip),
                    src=src,
                    dst=dst,
                ))
                cmd = 'scp {} {}{}:{}'.format(src, authentication, ip, dst)
            else:
                src = src[1:]
                puts("Getting {authentication}{ip}:{src} and saving in {dst}".format(
                    authentication=colored.green(authentication),
                    ip=colored.green(ip),
                    src=src,
                    dst=dst,
                ))
                cmd = 'scp {}{}:{} {}'.format(authentication, ip, src, dst)
            if extra:
                cmd += ' ' + ' '.join(extra)
            os.system(cmd)
        else:
            puts(colored.red("IP not found"))

    def ip(self, arguments):
        """
        Outputs ip of the mech machine.

        Usage: mech ip [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """

        vm = VMrun(self.vmx)
        ip = vm.getGuestIPAddress()
        if ip:
            puts(colored.green(ip))
        else:
            puts(colored.red("IP not found"))

    def provision(self, arguments):
        """
        Provisions the mech machine.

        Usage: mech provision [options]

        Options:
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def reload(self, arguments):
        """
        Restarts mech machine, loads new mechfile configuration.

        Usage: mech reload [options]

        Options:
                --provision                  Enable provisioning
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def port(self, arguments):
        """
        Displays information about guest port mappings.

        Usage: mech port [options]

        Options:
                --guest PORT                 Output the host port that maps to the given guest port
                --machine-readable           Display machine-readable output
                --name BOX                   Name of the box
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))

    def push(self, arguments):
        """
        Deploys code in this environment to a configured destination.

        Usage: mech push [options] [<strategy>]

        Options:
            -h, --help                       Print this help
        """
        puts(colored.red("Not implemented!"))
