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

"""Mech utility functions."""

from __future__ import division, absolute_import

import os
import re
import random
import string
import sys
import json
import tarfile
import fnmatch
import logging
import tempfile
import subprocess
import collections
from shutil import copyfile, rmtree

import requests
import click
from pypsrp.client import Client

from .vmrun import VMrun
import mech.vbm
from .mech_cloud_instance import MechCloudInstance

LOGGER = logging.getLogger('mech')


def main_dir():
    """Return the main directory."""
    return os.getcwd()


def mech_dir():
    """Return the mech directory."""
    return os.path.join(main_dir(), '.mech')


def makedirs(name, mode=0o777):
    """Make directories with mode supplied."""
    try:
        os.makedirs(name, mode)
    except OSError:
        pass


def start_vm(inst):
    """Start VM.
       inst is a MechInstance
    """
    LOGGER.debug('inst:%s', inst)
    started = None
    if inst.provider == 'vmware':
        # Note: user/password is needed for provisioning
        vmrun = VMrun(inst.vmx, user=inst.user, password=inst.password)
        click.secho("Bringing machine ({}) up...".format(inst.name), fg="blue")
        started = vmrun.start(gui=inst.gui)
    else:
        vbm = mech.vbm.VBoxManage()
        if inst.no_nat:
            bridge_adapter = preferred_interface()
            LOGGER.debug("bridge_adapter:%s", bridge_adapter)
            vbm.bridged(inst.name, bridge_adapter=bridge_adapter, quiet=False)
        else:
            vbm.create_hostonly(quiet=True)
            vbm.hostonly(inst.name, quiet=True)
        vbm.start(vmname=inst.name, gui=inst.gui, quiet=True)
        running_vms = vbm.list_running()
        started = None
        if inst.name in running_vms:
            started = True

    if started is None:
        click.secho("VM not started", fg="red")
    else:
        click.secho("Getting IP address...", fg="blue")
        ip_address = inst.get_ip(wait=True)

        if not inst.disable_shared_folders:
            # Note: virtualbox shared folders is before VM is started
            if inst.provider == 'vmware':
                share_folders(inst)
            else:
                # for virtualbox and shared folders, there are two steps:
                # first step is before boot (see above)
                # second step is to create mount point and mount it:
                virtualbox_share_folder_post_boot(inst)

        if ip_address:
            click.secho("VM ({})started on {}".format(inst.name, ip_address), fg="green")
        else:
            click.secho("VM ({}) started on an unknown "
                        "IP address".format(inst.name), fg="green")

        # if not already using preshared key, switch to it
        if not inst.use_psk and inst.auth:
            add_auth(inst)
            inst.switch_to_psk()

        if inst.remove_vagrant:
            del_user(inst, 'vagrant')

        if not inst.disable_provisioning:
            provision(inst, show=False)


def confirm(prompt, default='y'):
    """Confirmation prompt."""
    default = default.lower()
    if default not in ['y', 'n']:
        default = 'y'
    choicebox = '[Y/n]' if default == 'y' else '[y/N]'
    prompt = prompt + ' ' + choicebox + ' '

    while True:
        some_input = input(prompt).strip()
        if some_input == '':
            if default == 'y':
                return True
            else:
                return False

        if re.match('y(?:es)?', some_input, re.IGNORECASE):
            return True

        elif re.match('n(?:o)?', some_input, re.IGNORECASE):
            return False


def unpause_vm(inst):
    """Unpause a VM."""
    if inst.provider == 'vmware':
        vmrun = VMrun(inst.vmx)
        if vmrun.unpause(quiet=True) is not None:
            click.secho("Getting IP address...", fg="blue")
            ip_address = inst.get_ip(wait=True)
            if not inst.disable_shared_folders:
                share_folders(inst)
            else:
                click.secho("Disabling shared folders...", fg="blue")
                vmrun.disable_shared_folders(quiet=False)
            if ip_address:
                click.secho("VM resumed on {}".format(ip_address), fg="green")
            else:
                click.secho("VM resumed on an unknown IP address", fg="green")
        else:
            # Otherwise try starting
            start_vm(inst)
    else:
        vbm = mech.vbm.VBoxManage()
        if vbm.resume(inst.name, quiet=True) is not None:
            click.secho("Getting IP address...", fg="blue")
            ip_address = inst.get_ip(wait=True)
            # Note: disable_shared_folders is not really an option here
            if ip_address:
                click.secho("VM resumed on {}".format(ip_address), fg="green")
            else:
                click.secho("VM resumed on an unknown IP address", fg="green")
        else:
            # Otherwise try starting
            start_vm(inst)


def save_mechfile_entry(mechfile_entry, name, mechfile_should_exist=False):
    """Save the entry to the Mechfile."""
    LOGGER.debug('mechfile_entry:%s name:%s mechfile_should_exist:%s',
                 mechfile_entry, name, mechfile_should_exist)
    mechfile = load_mechfile(mechfile_should_exist)
    mechfile[name] = mechfile_entry
    LOGGER.debug("name:%s mechfile:%s", name, mechfile)
    return save_mechfile(mechfile)


def remove_mechfile_entry(name, mechfile_should_exist=True):
    """Removed the entry from the Mechfile."""
    LOGGER.debug('name:%s mechfile_should_exist:%s', name, mechfile_should_exist)
    mechfile = load_mechfile(mechfile_should_exist)

    if mechfile.get(name):
        del mechfile[name]

    LOGGER.debug("after removing name:%s mechfile:%s", name, mechfile)
    return save_mechfile(mechfile)


def save_mechfile(mechfile):
    """Save the mechfile object (which is a dict) to a file called 'Mechfile'.
       Return True if save was successful.
    """
    LOGGER.debug('mechfile:%s', mechfile)
    with open(os.path.join(main_dir(), 'Mechfile'), 'w+') as the_file:
        json.dump(mechfile, the_file, sort_keys=True, indent=2, separators=(',', ': '))
    return True


def locate(path, glob):
    """Locate a file in the path provided."""
    for root, _, filenames in os.walk(path):
        for filename in filenames:
            if fnmatch.fnmatch(filename, glob):
                return os.path.abspath(os.path.join(root, filename))


def parse_vmx(path):
    """Parse the virtual machine configuration (.vmx) file and return an
       ordered dictionary.
    """
    vmx = collections.OrderedDict()
    with open(path) as the_file:
        for line in the_file:
            line = line.strip().split('=', 1)
            if len(line) > 1:
                vmx[line[0].rstrip()] = line[1].lstrip()
    return vmx


def update_vmx(path, numvcpus=None, memsize=None, no_nat=False, add_custom_interface=None):
    """Update the virtual machine configuration (.vmx)
       file with desired settings.
    """
    updated = False

    vmx = parse_vmx(path)

    # Check if there is an existing interface
    has_network = False
    for vmx_key in vmx:
        if vmx_key.startswith('ethernet'):
            has_network = True

    # Write one if there is not
    if not has_network:
        vmx["ethernet0.addresstype"] = "generated"
        vmx["ethernet0.bsdname"] = "en0"
        if not no_nat:
            vmx["ethernet0.connectiontype"] = "nat"
        vmx["ethernet0.displayname"] = "Ethernet"
        vmx["ethernet0.linkstatepropagation.enable"] = "FALSE"
        vmx["ethernet0.pcislotnumber"] = "32"
        vmx["ethernet0.present"] = "TRUE"
        vmx["ethernet0.virtualdev"] = "e1000"
        vmx["ethernet0.wakeonpcktrcv"] = "FALSE"
        click.secho("Added network interface to vmx file", fg="yellow")
        updated = True

    # write out vmx file if memsize or numvcpus was specified
    if numvcpus is not None:
        vmx["numvcpus"] = '"{}"'.format(numvcpus)
        updated = True

    if memsize is not None:
        vmx["memsize"] = '"{}"'.format(memsize)
        updated = True

    if add_custom_interface is not None:
        vmx["ethernet1.connectionType"] = "custom"
        vmx["ethernet1.addressType"] = "generated"
        vmx["ethernet1.vnet"] = "VMnet" + '{}'.format(add_custom_interface)
        vmx["ethernet1.displayname"] = "VMnet" + '{}'.format(add_custom_interface)
        vmx["ethernet1.virtualDev"] = "e1000e"
        vmx["ethernet1.present"] = "TRUE"
        click.secho("Added custom network interface to vmx file", fg="yellow")
        updated = True

    if updated:
        with open(path, 'w') as new_vmx:
            for key in vmx:
                value = vmx[key]
                row = "{} = {}".format(key, value)
                new_vmx.write(row + os.linesep)


def load_mechfile(should_exist=True):
    """Load the Mechfile from disk and return the mechfile as a dictionary."""
    mechfile_fullpath = os.path.join(main_dir(), 'Mechfile')
    LOGGER.debug("mechfile_fullpath:%s", mechfile_fullpath)
    if os.path.isfile(mechfile_fullpath):
        with open(mechfile_fullpath) as the_file:
            try:
                mechfile = json.loads(the_file.read())
                LOGGER.debug('mechfile:%s', mechfile)
                return mechfile
            except ValueError:
                click.secho("Invalid Mechfile.", fg="red")
                return {}
    else:
        if should_exist:
            sys.exit(
                click.style(
                    "Could not find a Mechfile in the current directory. \n"
                    "A Mech environment is required to run this command. Run `mech init` \n"
                    "to create a new Mech environment. Or specify the name of the VM you would \n"
                    "like to start with `mech up <name>`. A final option is to change to a \n"
                    "directory with a Mechfile and to try again.", fg="red"))
        else:
            return {}


def default_shared_folders():
    """Return the default shared folders config.
    """
    return [{'share_name': 'mech', 'host_path': '.'}]


def build_mechfile_entry(location, box=None, name=None, box_version=None,
                         shared_folders=None, provider=None, windows=None):
    """Build the Mechfile from the inputs."""
    LOGGER.debug("location:%s name:%s box:%s box_version:%s provider:%s windows:%s",
                 location, name, box, box_version, provider, windows)
    mechfile_entry = {}

    if location is None:
        return mechfile_entry

    mechfile_entry['name'] = name
    mechfile_entry['box'] = box
    mechfile_entry['box_version'] = box_version
    mechfile_entry['provider'] = provider
    if windows is None:
        windows = False
    mechfile_entry['windows'] = windows

    if shared_folders is None:
        shared_folders = default_shared_folders()
    mechfile_entry['shared_folders'] = shared_folders

    if any(location.startswith(s) for s in ('https://', 'http://', 'ftp://')):
        if not name:
            name = 'first'
        mechfile_entry['url'] = location
        return mechfile_entry

    elif location.startswith('file:') or os.path.isfile(re.sub(r'^file:(?://)?', '', location)):
        if not name:
            name = 'first'
        location = re.sub(r'^file:(?://)?', '', location)
        LOGGER.debug('location:%s', location)
        mechfile_entry['file'] = location
        try:
            # see if the location/file is a json file
            with open(location) as the_file:
                # if an exception is not thrown, then set values and continue
                # to the end of the function
                catalog = json.loads(the_file.read())
                LOGGER.debug('catalog:%s', catalog)
        except (json.decoder.JSONDecodeError, ValueError):
            # this means the location/file is probably a .box file
            # or the json is invalid
            return mechfile_entry
        except IOError:
            # cannot open file
            sys.exit(click.style('Error: Cannot open file:({})'.format(location), fg="red"))
    else:
        try:
            account, box, ver = (location.split('/', 2) + ['', ''])[:3]
            if not account or not box:
                sys.exit(click.style("Provided box name is not valid", fg="red"))
            if ver:
                box_version = ver
            click.secho("Loading metadata for box '{}'{}".format(
                location, " ({})".format(box_version) if box_version else ""), fg="blue")
            url = 'https://app.vagrantup.com/{}/boxes/{}'.format(account, box)
            response = requests.get(url)
            response.raise_for_status()
            catalog = response.json()
        except (requests.HTTPError, ValueError) as exc:
            sys.exit(click.style("Bad response from HashiCorp's Vagrant "
                                 "Cloud API: %s" % exc), fg="red")
        except requests.ConnectionError:
            sys.exit(click.style("Couldn't connect to HashiCorp's Vagrant Cloud API", fg="red"))

    LOGGER.debug("catalog:%s name:%s box_version:%s", catalog, name, box_version)
    return catalog_to_mechfile(catalog, name=name, box=box,
                               box_version=box_version, provider=provider)


def catalog_to_mechfile(catalog, name=None, box=None, box_version=None, provider=None):
    """Convert the Hashicorp cloud catalog entry to Mechfile entry."""
    LOGGER.debug('catalog:%s name:%s box:%s box_version:%s', catalog, name, box, box_version)
    if provider is None:
        provider = 'vmware'
    mechfile = {}
    versions = catalog.get('versions', [])
    for ver in versions:
        current_version = ver['version']
        if not box_version or current_version == box_version:
            for a_provider in ver['providers']:
                if provider in a_provider['name']:
                    mechfile['name'] = name
                    mechfile['provider'] = provider
                    mechfile['box'] = catalog['name']
                    mechfile['box_version'] = current_version
                    mechfile['url'] = a_provider['url']
                    mechfile['shared_folders'] = default_shared_folders()
                    return mechfile
    sys.exit(click.style("Couldn't find a compatible VM using "
                         "catalog:{}".format(catalog), fg="red"))


def tar_cmd(*args, **kwargs):
    """Build the tar command to be used to extract the box."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
        # run the 'tar --help' command to see what capabilities are available
        proc = subprocess.Popen(['tar', '--help'], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, startupinfo=startupinfo, text=True)
    except OSError:
        return None
    if proc.returncode:
        return None
    stdoutdata, _ = proc.communicate()
    tar = ['tar']
    # if the tar_cmd has the option enabled *and* the capability was in the 'tar --help'
    # then append that option to the tar command (which is a list of strings)
    if kwargs.get('wildcards') and re.search(r'--wildcards\b', stdoutdata):
        tar.append('--wildcards')
    if kwargs.get('force_local') and re.search(r'--force-local\b', stdoutdata):
        tar.append('--force-local')
    if kwargs.get('fast_read') and sys.platform.startswith('darwin'):
        tar.append('--fast-read')
    tar.extend(args)
    return tar


def init_box(name, box=None, box_version=None, location=None, force=False, save=True,
             instance_path=None, numvcpus=None, add_custom_interface=None, memsize=None, no_nat=False, provider=None,
             windows=None):
    """Initialize the box. This includes uncompressing the files
       from the box file and updating the vmx file with
       desired settings (if vmware).

       Return the full path to the vmx or vbox file.

       VMware will just use the files as extracted.
       VirtualBox needs to "import" the ovf. It creates a .vbox file.
    """
    LOGGER.debug("name:%s box:%s box_version:%s location:%s provider:%s windows:%s",
                 name, box, box_version, location, provider, windows)
    if provider is None:
        provider = 'vmware'

    look_for = '*.vmx'
    vbox_path = None
    instance_path_save = instance_path
    if provider == 'virtualbox':
        look_for = '*.ovf'
        vbox_path = locate(instance_path, '*.vbox')
        # need to extract the files somewhere, then we will
        # remove them after importing to virtualbox
        if vbox_path != '':
            instance_path += '_tmp'

    # if we do not find the vmx file nor is the already imported files in place
    found_vmx_or_ovf = locate(instance_path, look_for)
    if not found_vmx_or_ovf and vbox_path != '':
        name_version_box = add_box(
            name=name,
            box=box,
            box_version=box_version,
            location=location,
            force=force,
            save=save,
            provider=provider,
            windows=windows)
        if not name_version_box:
            sys.exit(click.style("Cannot find a valid box with a VMX/OVF "
                                 "file in boxfile", fg="red"))

        box_parts = box.split('/')
        box_dir = os.path.join(*filter(None, (mech_dir(), 'boxes', provider,
                                              box_parts[0], box_parts[1], box_version)))
        box_file = locate(box_dir, '*.box')

        click.secho("Extracting box '{}'...".format(box_file), fg="blue")
        makedirs(instance_path)
        if sys.platform == 'win32':
            cmd = tar_cmd('-xf', box_file, force_local=True)
        else:
            cmd = tar_cmd('-xf', box_file)
        if cmd:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen(cmd, cwd=instance_path, startupinfo=startupinfo)
            if proc.wait():
                sys.exit(click.style("Cannot extract box", fg="red"))
        else:
            tar = tarfile.open(box_file, 'r')
            tar.extractall(instance_path)

        if not save and box.startswith(tempfile.gettempdir()):
            os.unlink(box)

    if provider == 'vmware':
        vmx_path = locate(instance_path, '*.vmx')
        if not vmx_path:
            sys.exit(click.style("Cannot locate a VMX file", fg="red"))
        update_vmx(vmx_path, numvcpus=numvcpus, memsize=memsize, no_nat=no_nat, add_custom_interface=add_custom_interface)
        return vmx_path
    else:
        ovf_path = locate(instance_path, '*.ovf')
        if not ovf_path:
            sys.exit(click.style("Cannot locate an OVF file", fg="red"))
        LOGGER.debug('ovf_path:%s', ovf_path)
        vbm = mech.vbm.VBoxManage()
        import_results = vbm.importvm(path_to_ovf=ovf_path, name=name,
                                      base_folder=mech_dir(), quiet=True)
        LOGGER.debug('import_results:%s', import_results)
        vbox_path = locate(instance_path_save, '*.vbox')
        if not vbox_path:
            sys.exit(click.style("Cannot locate a vbox file", fg="red"))
        # remove the extracted files
        rmtree(instance_path)
        return vbox_path


def add_box(name=None, box=None, box_version=None, location=None,
            force=False, save=True, provider=None, windows=None):
    """Add a box."""
    # build the dict
    LOGGER.debug('name:%s box:%s box_version:%s location:%s provider:%s windows:%s',
                 name, box, box_version, location, provider, windows)

    mechfile_entry = build_mechfile_entry(
        box=box,
        name=name,
        location=location,
        box_version=box_version,
        provider=provider,
        windows=windows)

    return add_mechfile(
        mechfile_entry,
        name=name,
        box=box,
        location=location,
        box_version=box_version,
        force=force,
        save=save,
        provider=provider,
        windows=windows)


def add_mechfile(mechfile_entry, name=None, box=None, box_version=None,
                 location=None, force=False, save=True, provider=None,
                 windows=None):
    """Add a mechfile entry."""
    LOGGER.debug('mechfile_entry:%s name:%s box:%s box_version:%s location:%s '
                 'provider:%s windows:%s', mechfile_entry, name, box,
                 box_version, location, provider, windows)

    box = mechfile_entry.get('box')
    name = mechfile_entry.get('name')
    box_version = mechfile_entry.get('box_version')
    provider = mechfile_entry.get('provider')
    windows = mechfile_entry.get('windows')

    url = mechfile_entry.get('url')
    box_file = mechfile_entry.get('file')

    if box_file:
        return add_box_file(box=box, box_version=box_version, filename=box_file,
                            force=force, save=save, provider=provider,
                            windows=windows)

    if url:
        return add_box_url(name=name, box=box, box_version=box_version,
                           url=url, force=force, save=save,
                           provider=provider, windows=windows)
    click.secho("Could not find a VMWare compatible VM for '{}'{}".format(
        name, " ({})".format(box_version) if box_version else ""), fg="red")


def add_box_url(name, box, box_version, url, force=False, save=True, provider=None, windows=None):
    """Add a box using the URL."""
    LOGGER.debug('name:%s box:%s box_version:%s url:%s provider:%s windows:%s',
                 name, box, box_version, url, provider, windows)
    box_parts = box.split('/')
    first_box_part = box_parts[0]
    second_box_part = ''
    if len(box_parts) > 1:
        second_box_part = box_parts[1]
    if provider is None:
        provider = 'vmware'
    box_dir = os.path.join(*filter(None, (mech_dir(), 'boxes', provider,
                                          first_box_part, second_box_part, box_version)))
    exists = os.path.exists(box_dir)
    if not exists or force:
        if exists:
            click.secho("Attempting to download provider:{} "
                        "box:'{}'...".format(provider, box), fg="blue")
        else:
            click.secho("Provider:{} Box:'{}' could not be found. "
                        "Attempting to download...".format(provider, box), fg="blue")
        try:
            click.secho("URL: {}".format(url), fg="blue")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            length = int(response.headers['content-length'])
            chunk_size = 1024 * 1024
            with click.progressbar(length=length, label="Downloading") as bar:
                the_file = tempfile.NamedTemporaryFile(delete=False)
                try:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            the_file.write(chunk)
                            bar.update(chunk_size)
                    the_file.close()
                    if response.headers.get('content-type') == 'application/json':
                        # Downloaded URL might be a Vagrant catalog if it's json:
                        catalog = json.load(the_file.name)
                        mechfile = catalog_to_mechfile(catalog, name, box, box_version)
                        return add_mechfile(
                            mechfile,
                            name=name,
                            box_version=box_version,
                            force=force,
                            save=save,
                            windows=windows)
                    else:
                        # Otherwise it must be a valid box:
                        return add_box_file(box=box, box_version=box_version,
                                            filename=the_file.name, url=url, force=force,
                                            save=save, provider=provider, windows=windows)
                finally:
                    os.unlink(the_file.name)
        except requests.HTTPError as exc:
            sys.exit(click.style(("Bad response: %s" % exc), fg="red"))
        except requests.ConnectionError:
            sys.exit(click.style(("Couldn't connect to '%s'" % url), fg="red"))
    return name, box_version, box


def add_box_file(box=None, box_version=None, filename=None, url=None,
                 force=False, save=True, provider=None, windows=None):
    """Add a box using a file as the source. Returns box and box_version."""
    click.secho("\nChecking integrity of provider:{} box:'{}' "
                "\nfilename:{}...".format(provider, box, filename), fg="blue")

    valid_endswith = 'vmx'
    look_for = '*.vmx'
    if provider == 'virtualbox':
        valid_endswith = 'ovf'
        look_for = '*.ovf'

    click.secho("looking for:{}...".format(look_for), fg="blue")
    if sys.platform == 'win32':
        cmd = tar_cmd('-tf', filename, look_for, wildcards=True, fast_read=True, force_local=True)
    else:
        cmd = tar_cmd('-tf', filename, look_for, wildcards=True, fast_read=True)

    if cmd:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(cmd, startupinfo=startupinfo)
        valid_tar = not proc.wait()
    else:
        tar = tarfile.open(filename, 'r')
        files = tar.getnames()
        valid_tar = False
        for i in files:
            if i.endswith(valid_endswith):
                valid_tar = True
                break
            if i.startswith('/') or i.startswith('..'):
                sys.exit(click.style("This box is comprised of filenames "
                                     "starting with '/' or '..' \n"
                                     "Exiting for the safety of your files.", fg="red"))

    if valid_tar:
        click.secho("Valid tar", fg="blue")
        if save:
            boxname = os.path.basename(url if url else filename)
            box = os.path.join(*filter(None, (mech_dir(), 'boxes', provider, box,
                                              box_version, boxname)))
            path = os.path.dirname(box)
            makedirs(path)
            if not os.path.exists(box) or force:
                copyfile(filename, box)
        else:
            box = filename
        return box, box_version


def get_info_for_auth(mech_use=False):
    """Get information (username/pub_key) for authentication."""
    username = os.getlogin()
    pub_key = os.path.expanduser('~/.ssh/id_rsa.pub')
    return {'auth': {'username': username, 'pub_key': pub_key, 'mech_use': mech_use}}


def init_mechfile(location=None, box=None, name=None, box_version=None, add_me=None,
                  use_me=None, provider=None, windows=None):
    """Initialize the Mechfile."""
    LOGGER.debug("name:%s box:%s box_version:%s location:%s add_me:%s use_me:%s"
                 " provider:%s windows:%s", name, box, box_version, location,
                 add_me, use_me, provider, windows)
    mechfile_entry = build_mechfile_entry(
        location=location,
        box=box,
        name=name,
        box_version=box_version,
        provider=provider,
        windows=windows)
    if add_me:
        mechfile_entry.update(get_info_for_auth(use_me))
    LOGGER.debug('mechfile_entry:%s', mechfile_entry)
    return save_mechfile_entry(mechfile_entry, name, mechfile_should_exist=False)


def add_to_mechfile(location=None, box=None, name=None, box_version=None, add_me=None,
                    use_me=None, provider=None, windows=None):
    """Add entry to the Mechfile."""
    LOGGER.debug("name:%s box:%s box_version:%s location:%s add_me:%s use_me:%s "
                 "provider:%s windows:%s", name, box, box_version, location,
                 add_me, use_me, provider, windows)
    this_mech_entry = build_mechfile_entry(
        location=location,
        box=box,
        name=name,
        box_version=box_version,
        provider=provider,
        windows=windows)
    if add_me:
        this_mech_entry.update(get_info_for_auth(use_me))
    LOGGER.debug('this_mech_entry:%s', this_mech_entry)
    return save_mechfile_entry(this_mech_entry, name, mechfile_should_exist=False)


def random_string(string_len=15):
    """Generate a random string of fixed length."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(string_len))


def add_auth(instance):
    """Add authentication to VM."""

    if not instance:
        sys.exit(click.style("Need to provide an instance to before "
                             "we can add authentication.", fg="red"))

    if instance.provider == 'vmware' and instance.vmx is None:
        sys.exit(click.style("Need to provide vmx before we can add authentication.", fg="red"))

    if instance.provider == 'virtualbox' and instance.vbox is None:
        sys.exit(click.style("Need to provide vbox before we can add authentication.", fg="red"))

    if instance.user is None or instance.user == '':
        sys.exit(click.style("Need to provide user to add authentication.", fg="red"))

    if instance.password is None or instance.password == '':
        sys.exit(click.style("Need to provide password to add authentication.", fg="red"))

    click.secho('Adding auth to instance:{}'.format(instance.name), fg="green")

    vmrun = VMrun(instance.vmx, instance.user, instance.password)
    # cannot run if vmware tools are not installed
    if not vmrun.installed_tools():
        sys.exit(click.style("Cannot add authentication if VMware Tools "
                             "are not installed.", fg="red"))

    if instance.auth:
        username = instance.auth.get('username', None)
        pub_key = instance.auth.get('pub_key', None)
        if username and pub_key:
            pub_key_path = os.path.expanduser(pub_key)
            LOGGER.debug("pub_key_path:%s pub_key:%s", pub_key_path, pub_key)
            with open(pub_key_path, 'r') as the_file:
                pub_key_contents = the_file.read().strip()
            if pub_key_contents:
                # set the password to some random string
                # user should never need it (sudo should not prompt for a
                # password)
                password = random_string()
                cmd = ('sudo useradd -m -s /bin/bash -p "{password}" {username};'
                       'sudo mkdir /home/{username}/.ssh;'
                       'sudo usermod -aG sudo {username};'
                       'echo "{username} ALL=(ALL) NOPASSWD: ALL" | '
                       'sudo tee -a /etc/sudoers;'
                       'echo "{pub_key_contents}" | '
                       'sudo tee -a /home/{username}/.ssh/authorized_keys;'
                       'sudo chmod 700 /home/{username}/.ssh;'
                       'sudo chown {username}:{username} /home/{username}/.ssh;'
                       'sudo chmod 600 /home/{username}/.ssh/authorized_keys;'
                       'sudo chown {username}:{username} /home/{username}/.ssh/authorized_keys'
                       ).format(username=username, pub_key_contents=pub_key_contents,
                                password=password)
                LOGGER.debug('cmd:%s', cmd)
                results = vmrun.run_script_in_guest('/bin/sh', cmd, quiet=True)
                LOGGER.debug('results:%s', results)
                if results is None:
                    click.secho("Did not add auth", fg="red")
                else:
                    click.secho("Added auth.", fg="red")
            else:
                click.secho("Could not read contents of the pub_key"
                            " file:{}".format(pub_key), fg="green")
        else:
            click.secho("Warning: Need a username and pub_key in auth.", fg="blue")
    else:
        click.secho("No auth to add.", fg="blue")


def vm_ready_based_on_state(state):
    """Return True if the state is one where we can communicate with it (scp/ssh, etc.)
    """
    if state in ["started", "powered on", "running", "unpaused"]:
        return True
    return False


def ssh(instance, command, plain=None, extra=None, command_args=None):
    """Run ssh command.

       Parameters:
          instance(MechInstance): a mech instance
          command(str): command to execute (ex: 'chmod +x /tmp/file')
          plain(bool): use user/pass auth
          extra(str): arguments to pass to ssh
          command_args(str): arguments for command

       Returns:
          return_code(int): 0=success
          stdout(str): Output from the command
          stderr(str): Error from the command

       Note: May not really need the tempfile if self.use_psk==True.
             Using the tempfile, there are options to not add host to the known_hosts files
             which is useful, but could be MITM attacks. Not likely locally, but still
             could be an issue.
    """
    LOGGER.debug('command:%s plain:%s extra:%s command_args:%s',
                 command, plain, extra, command_args)
    if instance.created:
        state = instance.get_vm_state()
        if vm_ready_based_on_state(state):
            config_ssh = instance.config_ssh()
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            try:
                temp_file.write(config_ssh_string(config_ssh).encode('utf-8'))
                temp_file.close()

                cmds = ['ssh']
                if not plain:
                    cmds.extend(('-F', temp_file.name))
                if not plain:
                    cmds.append(config_ssh['Host'])
                if extra:
                    cmds.append(extra)
                if command:
                    cmds.extend(('--', command))
                if command_args:
                    cmds.append(command_args)

                LOGGER.debug('cmds:%s', cmds)

                # if running a script
                if command:
                    result = subprocess.run(cmds, capture_output=True)
                    stdout = result.stdout.decode('utf-8').strip()
                    stderr = result.stderr.decode('utf-8').strip()
                    return result.returncode, stdout, stderr
                else:
                    # interactive
                    return subprocess.call(cmds), None, None
            finally:
                os.unlink(temp_file.name)
        else:
            return 1, '', 'VM not ready({})'.format(state)


def scp(instance, src, dst, dst_is_host, extra=None):
    """Run scp command.
       Note: May not really need the tempfile if self.use_psk==True.
             Using the tempfile, there are options to not add host to the known_hosts files
             which is useful, but could be MITM attacks. Not likely locally, but still
             could be an issue.
    """
    if instance.created:
        state = instance.get_vm_state()
        if vm_ready_based_on_state(state):
            config_ssh = instance.config_ssh()
            temp_file = tempfile.NamedTemporaryFile(delete=False)

            try:
                temp_file.write(config_ssh_string(config_ssh).encode())
                temp_file.close()

                cmds = ['scp']
                cmds.extend(('-F', temp_file.name))
                if extra:
                    cmds.extend(extra)

                host = config_ssh['Host']
                dst = '{}:{}'.format(host, dst) if dst_is_host else dst
                src = '{}:{}'.format(host, src) if not dst_is_host else src
                cmds.extend((src, dst))

                LOGGER.debug(
                    " ".join(
                        "'{}'".format(
                            c.replace(
                                "'",
                                "\\'")) if ' ' in c else c for c in cmds))
                result = subprocess.run(cmds, capture_output=True)
                stdout = result.stdout.decode('utf-8').strip()
                stderr = result.stderr.decode('utf-8').strip()
                return result.returncode, stdout, stderr
            finally:
                os.unlink(temp_file.name)
        else:
            return 1, '', 'VM not ready({})'.format(state)


def del_user(instance, username):
    """Delete a user in guest VM."""

    if not instance:
        sys.exit(click.style("Need to provide an instance before "
                             "we can delete user:{}.".format(username), fg="red"))

    if instance.vmx is None:
        sys.exit(click.style("VM must be created.", fg="red"))

    if instance.user is None:
        sys.exit(click.style("A user is required.", fg="red"))

    if username is None or username == '':
        sys.exit(click.style("A username to delete is required.", fg="red"))

    click.secho('Removing username ({}) from '
                'instance:{}...'.format(username, instance.name), fg="green")

    cmd = 'sudo userdel -fr {}'.format(username)
    LOGGER.debug('cmd:%s', cmd)
    ssh(instance=instance, command=cmd)


def provision(instance, show=False):
    """Provision an instance.

    Args:
        instance (MechInstance): an instance
        show (bool): just print the provisioning

    Notes:
        Valid provision types are:
           file: copies files to instances
           shell: executes scripts

    """

    if not instance:
        sys.exit(click.style("Need to provide an instance to provision().", fg="red"))

    if instance.provider == 'vmware' and instance.vmx is None:
        sys.exit(click.style("Need to provide vmx to provision().", fg="red"))

    if instance.provider == 'virtualbox' and instance.vbox is None:
        sys.exit(click.style("Need to provide vbox to provision().", fg="red"))

    if instance.user is None:
        sys.exit(click.style("Need to provide user to provision().", fg="red"))

    click.secho('Provisioning instance:{}'.format(instance.name), fg="green")

    provisioned = 0
    if instance.provision:
        for i, pro in enumerate(instance.provision):
            provision_type = pro.get('type')
            if provision_type == 'file':
                source = pro.get('source')
                destination = pro.get('destination')
                if show:
                    click.secho(" instance.name:{} provision_type:{} source:{} "
                                "destination:{}".format(instance.name, provision_type,
                                                        source, destination), fg="green")
                else:
                    click.secho("File provisioning (source:{} destination:{})".format(
                        source, destination), fg="green")
                    results = provision_file(instance, source, destination)
                    LOGGER.debug('results:%s', results)
                    if results is None:
                        click.secho("Not Provisioned", fg="red")
                        return
                provisioned += 1

            elif provision_type == 'shell':
                inline = pro.get('inline')
                path = pro.get('path')

                args = pro.get('args')
                if not isinstance(args, list):
                    args = [args]
                if show:
                    click.secho(" instance.name:{} provision_type:{} inline:{} path:{} "
                                "args:{}".format(instance.name, provision_type,
                                                 inline, path, args), fg="green")
                else:
                    click.secho("Inline shell provisioining (inline:{} path:{} args:{}".format(
                                inline, path, args), fg="green")
                    if provision_shell(instance, inline, path, args) is None:
                        click.secho("Not Provisioned", fg="red")
                        return
                provisioned += 1

            elif provision_type == 'ps':
                inline = pro.get('inline')
                path = pro.get('path')

                args = pro.get('args')
                if not isinstance(args, list):
                    args = [args]
                if show:
                    click.secho(" instance.name:{} provision_type:{} inline:{} path:{} "
                                "args:{}".format(instance.name, provision_type,
                                                 inline, path, args), fg="green")
                else:
                    click.secho("Inline ps provisioining (inline:{} path:{} args:{}".format(
                                inline, path, args), fg="green")
                    if provision_ps(instance, inline, path) is None:
                        click.secho("Not Provisioned", fg="red")
                        return
                provisioned += 1

            elif provision_type == 'pyinfra':
                path = pro.get('path')

                args = pro.get('args')
                if not isinstance(args, list):
                    args = [args]
                if show:
                    click.secho(" instance.name:{} provision_type:{} path:{} "
                                "args:{}".format(instance.name, provision_type,
                                                 path, args), fg="green")
                else:
                    click.secho("pyinfra provisioining (path:{} args:{}".format(
                                path, args), fg="green")
                    return_code, stdout, stderr = provision_pyinfra(instance, path, args)
                    if return_code is None:
                        click.secho("Not Provisioned", fg="red")
                        return
                    LOGGER.debug('return_code:%d stdout:%s stderr:%s', return_code, stdout, stderr)
                provisioned += 1

            else:
                click.secho("Not Provisioned - unknown provision type ({}) "
                            "(entries:{})".format(provision_type, i), fg="red")
                return
        else:
            click.secho("VM ({}) Provision {} "
                        "entries".format(instance.name, provisioned), fg="green")
    else:
        click.secho("Nothing to provision", fg="blue")


def winrm_copy(instance, local, remote):
    '''Copy file using winrm.'''
    suppress_urllib3_errors()
    client = Client(instance.get_ip(), username=instance.user,
                    password=instance.password, ssl=False)
    client.copy(local, remote)
    click.echo("Copied")
    # return code, stdout, stderr
    return 0, '', ''


def winrm_execute_cmd(instance, command):
    '''Run command prompt command using winrm.

       Returns:
          return_code
          stdout
          stderr
    '''
    LOGGER.debug('instance.name:%s command:%s', instance.name, command)
    suppress_urllib3_errors()
    client = Client(instance.get_ip(), username=instance.user,
                    password=instance.password, ssl=False)
    stdout, stderr, return_code = client.execute_cmd(command)
    LOGGER.debug('command:%s return_code:%d stdout:%s stderr:%s',
                 command, return_code, stdout, stderr)
    if stdout:
        click.echo(stdout.strip())
    if stderr:
        click.echo(stderr)
    return return_code, stdout, stderr


def winrm_execute_ps(instance, powershell, args=None):
    '''Run powershell using winrm.

       Returns:
          return_code
          stdout
          stderr (which will be '')
    '''
    LOGGER.debug('instance.name:%s powershell:%s args:%s', instance.name, powershell, args)
    suppress_urllib3_errors()

    powershell_with_args = powershell
    if args is not None:
        powershell_with_args = '{} {}'.format(powershell, args)

    client = Client(instance.get_ip(), username=instance.user,
                    password=instance.password, ssl=False)
    output, _, had_errors = client.execute_ps(powershell_with_args)
    LOGGER.debug('powershell:%s output:%s had_errors:%s', powershell, output, had_errors)

    return_code = 0
    if had_errors:
        return_code = 1
    if output:
        click.echo(output)
    return return_code, output, ''


def provision_file(instance, source, destination):
    """Provision from file.

    Args:
        instance (MechInstance): instance of the MechInstance class
        source (str): full path of a file to copy
        source (str): full path where the file is to be copied to

    Returns:
        return_code
        stdout
        stderr

    Notes:
       This function copies a file from host to guest.

    """
    click.secho("Copying ({}) to ({})".format(source, destination), fg="blue")
    if instance.windows is True:
        click.secho("Note: Windows instance.", fg="blue")
        return winrm_copy(instance, source, destination)
    else:
        return scp(instance, source, destination, True)


def create_tempfile_in_guest(instance):
    """Create a tempfile in the guest."""
    cmd = 'tmpfile=$(mktemp); echo $tmpfile'
    _, stdout, _ = ssh(instance=instance, command=cmd)
    return stdout


def winrm_create_tempfile_in_guest(instance):
    """Create a tempfile in the guest using wirrm."""
    ps = '$file=New-TemporaryFile; $file.fullname'
    _, stdout, _ = winrm_execute_ps(instance=instance, powershell=ps)
    return stdout


def provision_shell(instance, inline, script_path, args=None):
    """Provision from shell.

       Note: The script must be copied to guest, then run from there.

    Args:
        instance (MechInstance): instance of the MechInstance class
        inline (bool): run the script inline
        script_path (str): path to the script to run
        args (list of str): arguments to the script

    """
    if args is None:
        args = []
    tmp_path = create_tempfile_in_guest(instance)
    LOGGER.debug('inline:%s script_path:%s args:%s tmp_path:%s',
                 inline, script_path, args, tmp_path)
    if tmp_path is None or tmp_path == '':
        click.secho("Warning: Could not create tempfile in guest.", fg="red")
        return

    try:
        if script_path and os.path.isfile(script_path):
            click.secho("Configuring script {}...".format(script_path), fg="blue")
            results = scp(instance, script_path, tmp_path, True)
            if results is None:
                click.secho("Warning: Could not copy file to guest.", fg="red")
                return
        else:
            if script_path:
                if any(script_path.startswith(s) for s in ('https://', 'http://', 'ftp://')):
                    click.secho("Downloading {}...".format(script_path), fg="blue")
                    try:
                        response = requests.get(script_path)
                        response.raise_for_status()
                        inline = response.read()
                    except requests.HTTPError:
                        return
                    except requests.ConnectionError:
                        return
                else:
                    click.secho("Cannot open {}".format(script_path), fg="red")
                    return

            if not inline:
                click.secho("No script to execute", fg="red")
                return

            click.secho("Configuring script to run inline...", fg="blue")
            the_file = tempfile.NamedTemporaryFile(delete=False)
            try:
                the_file.write(str.encode(inline))
                the_file.close()
                scp(instance, the_file.name, tmp_path, True)
            finally:
                os.unlink(the_file.name)

        click.secho("Configuring environment...", fg="blue")
        make_executable = "chmod +x '{}'".format(tmp_path)
        LOGGER.debug('make_executable:%s', make_executable)
        if ssh(instance=instance, command=make_executable) is None:
            click.secho("Warning: Could not configure script in the environment.", fg="red")
            return

        click.secho("Executing program...", fg="blue")
        args_string = ' '.join([str(elem) for elem in args])
        LOGGER.debug('args:%s args_string:%s', args, args_string)
        return ssh(instance=instance, command=tmp_path, command_args=args_string)

    finally:
        return ssh(instance, 'rm -f "{}"'.format(tmp_path))


def provision_ps(instance, inline, script_path):
    """Provision from powershell.

       Notes:
          1) The script will be run from the host, not the guest.
          2) Args are not used at this time.

    Args:
        instance (MechInstance): instance of the MechInstance class
        inline (bool): run the script inline
        script_path (str): path to the script to run
        args (list of str): arguments to the script

    """
    LOGGER.debug('inline:%s script_path:%s', inline, script_path)

    ps = ''

    if script_path and os.path.isfile(script_path):
        # we have a local file with powershell, no need to download
        # just load into a variable
        with open(script_path, 'r') as script_file:
            ps = script_file.read().strip()
    else:
        if inline:
            # we have inline script to run
            ps = inline
        else:
            if script_path:
                if any(script_path.startswith(s) for s in ('https://', 'http://', 'ftp://')):
                    # looks like we need to download the powershell
                    click.secho("Downloading {}...".format(script_path), fg="blue")
                    try:
                        response = requests.get(script_path)
                        response.raise_for_status()
                        ps = response.read()
                    except requests.HTTPError:
                        return
                    except requests.ConnectionError:
                        return
                else:
                    click.secho("Cannot open {}".format(script_path), fg="red")
                    return
            else:
                click.secho("Need to provide inline or script to run powershell", fg="red")
                return

    click.secho("Executing powershell...({})".format(ps), fg="blue")
    return_code, stdout, stderr = winrm_execute_ps(instance=instance,
                                                   powershell=ps)
    return return_code, stdout, stderr


def provision_pyinfra(instance, script_path, args=None):
    """Provision using pyinfra.

    Args:
        instance (MechInstance): instance of the MechInstance class
        script_path (str): path to the script to run, must end with .py
        args (list of str): arguments to the script

    Return:
        return_code(int): return code of the process (0=success)
        stdout(str): standard output
        stderr(str): standard error


    """
    if args is None:
        args = []

    LOGGER.debug('instance.name:%s script_path:%s args:%s', instance.name, script_path, args)

    if script_path and os.path.isfile(script_path):
        return run_pyinfra_script(instance.get_ip(), instance.user,
                                  password=instance.password,
                                  script_path=script_path, args=args)
    else:
        if script_path:
            if any(script_path.startswith(s) for s in ('https://', 'http://', 'ftp://')):
                click.secho("Downloading {}...".format(script_path), fg="blue")
                try:
                    response = requests.get(script_path)
                    response.raise_for_status()
                    pyinfra_remote_contents = response.text
                except requests.HTTPError:
                    return
                except requests.ConnectionError:
                    return
            else:
                click.secho("Cannot open {}".format(script_path), fg="red")
                return

        LOGGER.debug('pyinfra_remote_contents:%s', pyinfra_remote_contents)
        the_file = tempfile.NamedTemporaryFile(delete=False, suffix='.py')
        try:
            the_file.write(str.encode(pyinfra_remote_contents))
            the_file.close()
            return run_pyinfra_script(host=instance.get_ip(), username=instance.user,
                                      password=instance.password,
                                      script_path=the_file.name, args=args)
        finally:
            os.unlink(the_file.name)


def pyinfra_installed():
    """Return True if the utility 'pyinfra' is installed, otherwise return False.
    """
    results = subprocess.run("pyinfra --version", shell=True, capture_output=True)
    return results.returncode == 0


def run_pyinfra_script(host, username, password=None, script_path=None, args=None):
    """Run a pyinfra script on host.

       Parameters
         - host(string): hostname to run the pyinfra script against, can be either
                       a hostname or ip address
         - username(string): username to use for the authentication to the host
         - password(string): password to use for the authentication to the host,
                             if no password, assume pre-shared key
         - script_path(string): the path of of the pyinfra script
         - args(kwargs): arguments to pass to running the script

       Returns:
         - return_code(int): return code from the run example: 0=success
         - stdout(string): output from the run
         - stderr(string): errors from the run

    """
    LOGGER.debug("host:%s username:%s script_path:%s args:%s",
                 host, username, script_path, args)
    if args is None:
        args = []

    if host is None or host == '':
        click.secho("Warning: A host is required for pyinfra provisioning.", fg="red")
        return

    if username is None or username == '':
        click.secho("Warning: A username is required for pyinfra provisioning.", fg="red")
        return

    if script_path is None or script_path == '':
        click.secho("Warning: A script is required for pyinfra provisioning.", fg="red")
        return

    if not os.path.exists(script_path):
        click.secho("Warning: Could not find the pyinfra "
                    "script ({}).".format(script_path), fg="red")
        return

    if not script_path.endswith('.py'):
        click.secho("Warning: A pyinfra provisioning script must end with .py.", fg="red")
        return

    is_pyinfra_installed = pyinfra_installed()
    if not is_pyinfra_installed:
        click.secho("Warning: pyinfra must be installed.", fg="red")
        return

    click.secho("Going to run ({}) using args({}) on host:{} authenticating with username:{}".
                format(script_path, args, host, username), fg="green")

    user_auth = '--user "{}"'.format(username)
    if password is not None:
        user_auth += ' --password "{}"'.format(username, password)
    command = "pyinfra {host} {user_auth} {script}".format(host=host, user_auth=user_auth,
                                                           script=script_path)
    LOGGER.debug('About to run this pyinfra command:%s', command)
    results = subprocess.run(command, shell=True, capture_output=True)
    stdout = results.stdout.decode('utf-8')
    stderr = results.stderr.decode('utf-8')
    return results.returncode, stdout, stderr


def config_ssh_string(config_ssh):
    """Build the ssh-config string from a dict holding the keys/values."""
    ssh_config = "Host {}".format(config_ssh.get('Host', '')) + os.linesep
    for key, value in config_ssh.items():
        if key != 'Host':
            ssh_config += "  {} {}".format(key, value) + os.linesep
    return ssh_config


def share_folders(inst):
    """Share folders.
    Args:
        inst (MechInstance): an instance of the MechInstance class (representing a vm)

    """
    if not inst.disable_shared_folders:
        click.secho("Sharing folders...", fg="blue")

        if inst.provider == 'vmware':
            vmrun = VMrun(inst.vmx)
            vmrun.enable_shared_folders(quiet=False)
        else:
            vbm = mech.vbm.VBoxManage()

        for share in inst.shared_folders:
            share_name = share.get('share_name')
            host_path = share.get('host_path')
            if host_path == '.':
                host_path = main_dir()
            absolute_host_path = os.path.abspath(host_path)
            click.secho("share:{} host_path:{} => "
                        "absolute_host_path:{}".format(share_name, host_path,
                                                       absolute_host_path), fg="blue")
            if inst.provider == 'vmware':
                vmrun.add_shared_folder(share_name, host_path, quiet=True)
            else:
                # for virtualbox, the path must be absolute
                vbm.sharedfolder_add(inst.name, share_name, absolute_host_path)


def virtualbox_share_folder_post_boot(inst):
    """For virtualbox, we need to create a mount point and mount the share."""
    for share in inst.shared_folders:
        share_name = share.get('share_name')
        command = ("sudo mkdir -p /mnt/{share_name};"
                   "sudo mount -t vboxsf {share_name}"
                   " /mnt/{share_name}").format(share_name=share_name)
        ssh(instance=inst, command=command)


def get_fallback_executable(command_name='vmrun'):
    """Get a fallback executable for a command line tool."""
    if 'PATH' in os.environ:
        LOGGER.debug("os.environ['PATH']:%s", os.environ['PATH'])
        for path in os.environ['PATH'].split(os.pathsep):
            vmrun = os.path.join(path, command_name)
            if os.path.exists(vmrun):
                return vmrun
            vmrun = os.path.join(path, command_name + '.exe')
            if os.path.exists(vmrun):
                return vmrun
    return None


def valid_provider(provider):
    """Determine if the provider provided is supported and valid.
       Returns True if it is valid or False if it is not valid.
    """
    if provider in ('vmware', 'virtualbox'):
        return True
    else:
        return False


def get_darwin_executable(command_name='vmrun'):
    """Get the full path for the command to run on a mac host."""
    if command_name == 'vmrun':
        full_command = '/Applications/VMware Fusion.app/Contents/Library/vmrun'
    else:
        full_command = '/usr/local/bin/VBoxManage'
    if os.path.exists(full_command):
        return full_command
    return get_fallback_executable()


def get_win32_executable():
    """Get the full path for the 'vmrun' command on a Windows host.
    """
    import winreg
    reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    try:
        key = winreg.OpenKey(reg, 'SOFTWARE\\VMware, Inc.\\VMware Workstation')
        try:
            return os.path.join(winreg.QueryValueEx(key, 'InstallPath')[0], 'vmrun.exe')
        finally:
            winreg.CloseKey(key)
    except WindowsError:
        key = winreg.OpenKey(reg, 'SOFTWARE\\WOW6432Node\\VMware, Inc.\\VMware Workstation')
        try:
            return os.path.join(winreg.QueryValueEx(key, 'InstallPath')[0], 'vmrun.exe')
        finally:
            winreg.CloseKey(key)
    finally:
        reg.Close()
    return get_fallback_executable()


def get_provider(vmrun_executable):
    """
    Identifies the right hosttype for vmrun command (ws | fusion | player)
    """

    if sys.platform == 'darwin':
        return 'fusion'

    for provider in ['ws', 'player', 'fusion']:
        # To determine the provider, try
        # running the vmrun command to see which one works.
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.Popen([vmrun_executable,
                                     '-T',
                                     provider,
                                     'list'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    startupinfo=startupinfo)
        except OSError:
            pass

        proc.communicate()
        if proc.returncode == 0:
            return provider


def save_mechcloudfile(inst):
    """Save the inst (which is a dict) to a file called 'Mechcloudfile'.
       Return True if save was successful.
    """
    LOGGER.debug('inst:%s', inst)
    with open(os.path.join(main_dir(), 'Mechcloudfile'), 'w+') as the_file:
        json.dump(inst, the_file, sort_keys=True, indent=2, separators=(',', ': '))
    return True


def remove_mechcloudfile_entry(name, should_exist=True):
    """Remove an entry from the Mechcloudfile."""
    LOGGER.debug('name:%s should_exist:%s', name, should_exist)
    clouds = load_mechcloudfile(should_exist)

    if clouds.get(name):
        del clouds[name]

    LOGGER.debug("after removing name:%s clouds:%s", name, clouds)
    return save_mechcloudfile(clouds)


def load_mechcloudfile(should_exist=True):
    """Load the Mechcloudfile from disk and return as a dictionary."""
    fullpath = os.path.join(main_dir(), 'Mechcloudfile')
    LOGGER.debug("fullpath:%s", fullpath)
    if os.path.isfile(fullpath):
        with open(fullpath) as the_file:
            try:
                clouds = json.loads(the_file.read())
                LOGGER.debug('clouds:%s', clouds)
                return clouds
            except ValueError:
                click.secho("Invalid Mechcloudfile.", fg="red")
                return {}
    else:
        if should_exist:
            sys.exit(
                click.style(
                    "Could not find a Mechcloudfile in the current directory. \n"
                    "A Mech Cloud configuration is required to run this command.\n"
                    "Run `mech cloud init` to create a new Mech Cloud environment.", fg="red"))
        else:
            return {}


def cloud_exists(cloud_name):
    """Return True if the cloud exists in the Mechcloudfile."""
    if cloud_name is None or cloud_name == '':
        return False
    clouds = load_mechcloudfile(False)
    if clouds.get(cloud_name) is not None:
        return True
    else:
        return False


def ssh_with_username(hostname, username, command):
    """Run the command on a host using the username.
    """
    if hostname != '' and username != '' and command != '':
        command = 'ssh {username}@{hostname} -- {command}'.format(username=username,
                                                                  hostname=hostname,
                                                                  command=command)

        LOGGER.debug('command:%s', command)
        result = subprocess.run(command, shell=True, capture_output=True)
        stdout = result.stdout.decode('utf-8')
        stderr = result.stderr.decode('utf-8')
        return result.returncode, stdout, stderr


def report_provider(provider):
    """Check if this provider is available."""
    okay = True
    if not valid_provider(provider):
        click.secho("Invalid provider ({})".format(provider), fg="red")
        okay = False
    if provider == 'vmware':
        vmrun = VMrun()
        if not vmrun.installed():
            click.secho("Warning: Provider is not available.", fg="red")
            click.secho("Install VMware or change provider.", fg="red")
            okay = False
    elif provider == 'virtualbox':
        vbm = mech.vbm.VBoxManage()
        if not vbm.installed():
            click.secho("Warning: Provider is not available.", fg="red")
            click.secho("Install Virtualbox or change provider.", fg="red")
            okay = False
    return okay


def kill_pids(pids):
    """Kill all pids."""
    for pid in pids:
        results = subprocess.run(args='kill {}'.format(pid), shell=True, capture_output=True)
        if results.returncode != 0:
            click.secho("Could not kill pid:{}".format(pid))


def find_pids(search_string):
    """Return all pids that that match the search_string."""
    pids = []
    results = subprocess.run(args="ps -ef | grep '{}' | grep -v grep"
                             .format(search_string), shell=True, capture_output=True)
    if results.returncode == 0:
        # we found a proc
        stdout = results.stdout.decode('utf-8')
        for line in stdout.split('\n'):
            data = line.split()
            if len(data) > 2:
                # add pid to the collection
                pids.append(data[1])
    return pids


def cleanup_dir_and_vms_from_dir(a_dir, names=None, all_vms=False):
    """Kill processes and remove directory and re-create the directory.
       For VMware VMs, look for the .vmx part_of_dir matches the full path.
       For virtualbox look 'VBoxHeadless --comment <name of the instance>'
       Note: Unfortunately, the name is global, so you can only have one
       'first' instance. Make instance name unique for int tests that use
       virtualbox.
       Use a_dir to '' and all_vms=True to kill and remove all.
   """
    if names is None:
        names = ['first']
    # remove from virtualbox
    for name in names:
        subprocess.run(args="VBoxManage unregistervm {}".format(name),
                       shell=True, capture_output=True)
    # kill vmware processes
    kill_pids(find_pids('vmware-vmx.*' + a_dir + '/.mech/'))
    # try to stop, then kill virtualbox processes (if any), then unregister
    for name in names:
        subprocess.run(args="VBoxManage controlvm {} poweroff".format(name),
                       shell=True, capture_output=True)
        kill_pids(find_pids('VBoxHeadless --comment {} '.format(name)))
        subprocess.run(args="VBoxManage unregistervm {} --delete".format(name),
                       shell=True, capture_output=True)
    # clean up the vm files
    rmtree(a_dir, ignore_errors=True)
    # remove any "dead" instances in virtualbox
    results = subprocess.run(args="VBoxManage list vms", shell=True, capture_output=True)
    stdout = results.stdout.decode('utf-8')
    vms = stdout.split('\n')
    LOGGER.debug('vms:%s', vms)
    for line in vms:
        parts = line.split(' ')
        if all_vms:
            if len(parts) > 1:
                vm = parts[1]
                LOGGER.debug('vm:%s', vm)
                # try to stop it first (in case the vm is "locked")
                subprocess.run(args="VBoxManage controlvm {} poweroff".format(vm),
                               shell=True, capture_output=True)
                subprocess.run(args="VBoxManage unregistervm {} --delete".format(vm),
                               shell=True, capture_output=True)
        else:
            if len(parts) > 1 and parts[0] == '"<inaccessible>"':
                vm = parts[1]
                LOGGER.debug('vm:%s', vm)
                # try to stop it first (in case the vm is "locked")
                subprocess.run(args="VBoxManage controlvm {} poweroff".format(vm),
                               shell=True, capture_output=True)
                subprocess.run(args="VBoxManage unregistervm {} --delete".format(vm),
                               shell=True, capture_output=True)
    # re-create the directory to start afresh
    if a_dir != '':
        os.mkdir(a_dir)


def get_interfaces():
    """Get the network interfaces.
       We may have 'ifconfig' or 'ip' installed.
    """
    interfaces = []

    # first try "ifconfig"
    results = subprocess.run(args='ifconfig', shell=True, capture_output=True)
    if results.returncode == 0:
        each_line = results.stdout.decode('utf-8').split('\n')
        for line in each_line:
            print('line:{}'.format(line))
            if len(line) > 0 and line[0] != ' ' and line[0] != '\t':
                parts = line.split()
                if len(parts) > 1:
                    if parts[0].endswith(':'):
                        interfaces.append(parts[0][:-1])
        return interfaces
    else:
        # try "ip"
        results = subprocess.run(args='ip addr', shell=True, capture_output=True)
        if results.returncode == 0:
            each_line = results.stdout.decode('utf-8').split('\n')
            for line in each_line:
                parts = line.split()
                if len(parts) > 2:
                    if parts[1].endswith(':'):
                        interfaces.append(parts[1][:-1])
            return interfaces
    return interfaces


def preferred_interface():
    """Guess the preferred network interface to use as bridge.
       This is a hack.
    """
    interfaces = get_interfaces()
    LOGGER.debug('interfaces:%s', interfaces)
    for interface in interfaces:
        if interface == 'en0':
            return 'en0'
        if interface == 'eno1':
            return 'eno1'
        if interface == 'eth0':
            return 'eth0'
        if interface == 'enp5s0':
            return 'enp5s0'
    return "en0"


def suppress_urllib3_errors():
    """Suppress the urllib3 errors."""
    # Note: Not really sure why we need to do this, but it seems to suppress the output
    # when using the pypsrp client.
    try:
        from urllib3.connectionpool import log
        log.addFilter(SuppressFilter())
    except:  # noqa: E722
        pass


class SuppressFilter(logging.Filter):
    def filter(self, record):
        return 'unparsed data' not in record.getMessage()


def instances():
    """Return list of instances."""
    return list(load_mechfile())


def cloud_instances():
    """Return list of cloud instances."""
    return list(load_mechcloudfile())


def cloud_run(cloud_name, operations):
    """Run the command on the cloud instance.
    """
    if cloud_name and cloud_name != '':
        mci = MechCloudInstance(cloud_name)
        mci.read_config(cloud_name)

        # find out what args were used on the command line
        # any command after the operation will be appended to
        # the command to run on the remote
        args_list = []
        found_operation = False
        LOGGER.debug('sys.argv:%s', sys.argv)
        for arg in sys.argv:
            if arg in operations:
                found_operation = True
            if found_operation:
                args_list.append(arg)
        args_string = ' '.join(args_list)
        LOGGER.debug('cloud_name:%s operations:%s args_list:%s args_string:%s',
                     cloud_name, operations, args_list, args_string)
        command = ('''ssh {username}@{hostname} -- "cd {directory}; '''
                   '''source {directory}/venv/bin/activate && '''
                   '''mech {args_string}"''').format(hostname=mci.hostname,
                                                     directory=mci.directory,
                                                     username=mci.username,
                                                     args_string=args_string)
        LOGGER.debug('command:%s', command)
        result = subprocess.run(command, shell=True, capture_output=True)
        stdout = result.stdout.decode('utf-8')
        stderr = result.stderr.decode('utf-8')
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr)
        return result.returncode, stdout, stderr


# for short and long help options
def context_settings():
    return dict(help_option_names=['-h', '--help'])
