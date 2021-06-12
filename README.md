# mech

![Python package](https://github.com/mkinney/mech/workflows/Python%20package/badge.svg)
[![codecov](https://codecov.io/gh/mkinney/mech/branch/master/graph/badge.svg)](https://codecov.io/gh/mkinney/mech)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mikemech)

NOTE: The Hashicorp VMware vagrant provider is now open source. See https://github.com/hashicorp/vagrant-vmware-desktop 

# Update 2021-06-09 - I'm not sure there will be a need for this tool any longer due to vagrant being free.

Feel free to fork this project.

Please test and provide any feedback/issues.

*Newly added virtualbox functionality.* By default, the provider will be `vmware`. Tested on Ubuntu (using VMware Workstation and VirtualBox) and Mac (using VirtualBox and VMware Fusion).

Did you know you can now *provision* using `pyinfra`? See `mech provision --help` for more info or look at [one of the integration tests](https://github.com/mkinney/mech/blob/master/tests/int/provision/Mechfile#L59) for how to specify `pyinfra` provisioning from a remote file. You can also have local files for provisioning.

*Newly added `mech cloud` capability.* See `mech cloud --help` for more info. Ever want to start a VM on another desktop/laptop? With 'mech cloud' you can do just that. 'mech cloud' is similar to the the [docker context](https://docs.docker.com/engine/reference/commandline/context/) option. (Note: 'mech cloud' was written before discovering 'docker context', otherwise would have borrowed some of docker's interface/terms.)

There is `--help` on every operation.

# mech --help
```
Usage: mech [OPTIONS] COMMAND [ARGS]...

  Mech is a command line utility for virtual machine automation.

  Create, start, stop, destroy virtual machines (aka instances) with ease.

  VMware Fusion, VMware Workstation, and/or Oracle VirtualBox can be used.

  Mech is similar to Hashicorp's vagrant utility.

Options:
  --debug
  --cloud TEXT
  --version     Show the version and exit.
  -h, --help    Show this message and exit.

Commands:
  add            Add instance to the Mechfile.
  box            Box operations.
  cloud          Cloud operations.
  destroy        Stops and deletes all traces of the instances.
  down           Stops the instance(s).
  global-status  Outputs info about all instances running on this host and...
  init           Initialize Mechfile.
  ip             Outputs the IP address of the instance.
  list           Lists all available instances (using Mechfile)
  pause          Pauses the instance(s).
  port           Displays guest port mappings.
  provision      Provision the instance(s).
  ps             List running processes in Guest OS.
  remove         Remove instance from the Mechfile.
  resume         Resume paused/suspended instance(s).
  scp            Copies files to and from the instance using SCP.
  snapshot       Snapshot operations.
  ssh            Connects to an instance via SSH or runs a command (if...
  ssh-config     Output OpenSSH configuration to connect to the instance.
  support        Show support info.
  suspend        Suspends the instance(s).
  up             Starts and provisions instance(s).
  upgrade        Upgrade the VM and virtual hardware for the instance(s).
  winrm          Winrm operations.
```


For help on any individual command run `mech <command> -h`

All "state" will be saved in .mech directory. (boxes and instances)

Examples:

Initializing and using a box from HashiCorp's Vagrant Cloud:

```
    mech init bento/ubuntu-18.04
    mech up
    mech ssh
```

If having a problem with a command, add the "--debug" option like this:

```
    mech --debug up
```

# mech up --help
```
% mech up --help
Usage: mech up [OPTIONS] [INSTANCE]

  Starts and provisions instance(s).

  Notes:

  If no instance is specified, all instances will be started.

  The options ('memsize', 'numvcpus', add-custom-interface, and 'no-nat') will only be applied
  upon first run of the 'up' command.

  The 'no-nat' option will only be applied if there is no network interface
  supplied in the box file for 'vmware'. For 'virtualbox', if you need
  internet access from the vm, then you will want to use 'no-nat'. Interface
  'en0' will be used for bridge.

  Unless 'disable-shared-folders' is used, a default read/write share called
  'mech' will be mounted from the current directory. '/mnt/hgfs/mech' on
  'vmware' and '/mnt/mech' on 'virtualbox' To add/change shared folders,
  modify the Mechfile directly, then stop/start the VM.

  The 'remove-vagrant' option will remove the vagrant account from the guest
  VM which is what 'mech' uses to communicate with the VM. Be sure you can
  connect/admin the instance before using this option. Be sure to check that
  root cannot ssh, or change the root password.

Options:
  --disable-provisioning        Do not provision.
  --disable-shared-folders      Do not share folders.
  --gui                         Start GUI, otherwise starts headless.
  --memsize MEMORY              Specify memory size in MB.
  --no-cache                    Do not save the downloaded box.
  --no-nat                      Do not use NAT networking (i.e., use bridged).
  --numvcpus VCPUS              Specify number of vcpus.
  --add-custom-interface VMNET  Add a custom netowrk interface (i.e., 3 for VMnet3)
  -r, --remove-vagrant          Remove vagrant user.
  -h, --help                    Show this message and exit.
```

# Example using mech

Initializing and using a machine from HashiCorp's Vagrant Cloud:

```
    mech init bento/ubuntu-18.04
    mech up
    mech ssh
```

`mech init` can be used to pull a box file which will be installed and
generate a Mechfile in the current directory. You can also pull boxes
from Vagrant Cloud with `mech init freebsd/FreeBSD-11.1-RELEASE`.
See the `mech up -h` page for more information.

Can have multiple instances of the same box. The default instance name is 'first'.

Here is the help info for adding a new instance:

# mech add --help
```
% mech add -h
Usage: mech add [OPTIONS] NAME LOCATION

  Add instance to the Mechfile.

  Notes:

  The 'add-me' option will add the currently logged in user to the guest,
  add the same user to sudoers, and add the id_rsa.pub key to the
  authorized_hosts file for that user.

Options:
  -a, --add-me           Add the current user/pubkey to guest.
  --box BOXNAME          Name of the box (ex: bento/ubuntu-10.04).
  --box-version VERSION  Constrain to specific box version.
  --provider PROVIDER    Provider (`vmware` or `virtualbox`)
  -u, --use-me           Use the current user for mech interactions.
  -w, --windows          Windows instance
  -h, --help             Show this message and exit.
```

# mech list
Here is what it would look like having multiple instance with different providers:
```
% mech list
                NAME	        ADDRESS	                                BOX	     VERSION	    PROVIDER	       STATE
               first	  192.168.3.134	                 bento/ubuntu-18.04	 201912.04.0	      vmware	     started
              second	 192.168.56.194	                 bento/ubuntu-18.04	 202002.04.0	  virtualbox	     running
               third	     notcreated	              mrlesmithjr/alpine311	  1578437753	  virtualbox	  notcreated
```

# Installation

To install:

`pip install -U mikemech`

or for the latest:

`pip install -U git+https://github.com/mkinney/mech.git`

# Shared Folders

If the box you init was created properly, you will be able to access
the host's current working directory in `/mnt/hgfs/mech`. If you are
having trouble with an Ubuntu guest, try running:

```bash
sudo apt-get update
sudo apt-get install linux-headers-$(uname -r) open-vm-tools
```

followed by

```bash
sudo vmware-config-tools.pl
```

or

```bash
vmhgfs-fuse .host:/mech /mnt/hgfs
```

# Want zsh completion for commands/options (aka "tab completion")?
1. add these lines to ~/.zshrc

```bash
# folder of all of your autocomplete functions
fpath=($HOME/.zsh-completions $fpath)
# enable autocomplete function
autoload -U compinit
compinit
```

2. Copy script to something in fpath (Note: Run `echo $fpath` to show value.)

```bash
cp _mech ~/.zsh-completions/
```

3. Reload zsh

```bash
exec zsh
```

4. Try it out by typing `mech <tab>`. It should show the options available.

# Want bash completion for commands/options (aka "tab completion")?
1. add these lines to ~/.bash_profile

```bash
[ -f /usr/local/etc/bash_completion ] && . /usr/local/etc/bash_completion
```

2. Copy script to path above

```bash
cp mech_completion.sh /usr/local/etc/bash_completion/
```

3. Reload .bash_profile

```bash
source ~/.bash_profile
```

4. Try it out by typing `mech <tab>`. It should show the options available.

# Background

One of the authors made this because they don't like VirtualBox and wanted to use vagrant
with VMmare Fusion but was too cheap to buy the Vagrant plugin.

https://blog.kchung.co/mech-vagrant-with-vmware-integration-for-free/

