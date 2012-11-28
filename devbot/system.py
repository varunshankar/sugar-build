import json
import os
import subprocess
import sys

from devbot import config
from devbot import distro
from devbot import command
from devbot import state
from devbot import utils
from devbot import xvfb

libdirs = ["lib",
           "lib64",
           "lib/x86_64-linux-gnu",
           "lib/i386-linux-gnu"]

def check_binary(check):
    return subprocess.call(["which", check],
                           stdout=utils.devnull,
                           stderr=subprocess.STDOUT)

def check_pkgconfig(check):
    return subprocess.call(["pkg-config", "--exists", check]) == 1

def check_python(check):
    return subprocess.call(["python", "-c", check],
                           stdout=utils.devnull,
                           stderr=subprocess.STDOUT) == 1

def check_gtkmodule(check):
    # Not sure we can do better than this, the gtkmodule stuff is private
    missing = True
    
    for libdir in libdirs:
        if os.path.exists("/usr/%s/gtk-2.0/modules/lib%s.so" % (libdir, check)):
            missing = False

    return missing

def check_include(check):
    return not os.path.exists(os.path.join("/usr/include/", check))

def check_dbus(check):
    return not os.path.exists("/usr/share/dbus-1/services/%s.service" % check)

def check_metacity_theme(check):
    return not os.path.exists("/usr/share/themes/%s/metacity-1/metacity-theme-3.xml" % check)

def check_gstreamer(check, version):
    missing = True
    
    for libdir in libdirs:
        if os.path.exists("/usr/%s/gstreamer-%s/libgst%s.so" % \
                          (libdir, version, check)):
            missing = False

    return missing

def check_gstreamer_0_10(check):
    return check_gstreamer(check, "0.10")

def check_gstreamer_1_0(check):
    return check_gstreamer(check, "1.0")

checkers = { "binary": check_binary,
             "python": check_python,
             "pkgconfig": check_pkgconfig,
             "gtkmodule": check_gtkmodule,
             "dbus": check_dbus,
             "gstreamer-0.10": check_gstreamer_0_10,
             "gstreamer-1.0": check_gstreamer_1_0,
             "metacity-theme": check_metacity_theme,
             "include": check_include }

def _print_checks(checks):
    for check in checks:
        print "[%s] %s" % (check["checker"], check["check"])

def run_checks(package_manager, checks, packages):
    distro_info = distro.get_distro_info()

    failed_checks = []
    packages_not_found = []
    to_install = []

    for check in checks:
        checker = checkers[check["checker"]]
        if checker(check["check"]):
            if distro_info.name in packages[check["name"]]:
                for package in packages[check["name"]][distro_info.name]:
                    # Might be none, if so skip on this distro_name
                    if package and package not in to_install:
                        to_install.append(package)
            else:
                packages_not_found.append(check)

            failed_checks.append(check)

    if distro_info.supported:
        if packages_not_found:
            print "\Packages not found for"
            _print_checks(_packages_not_found)
            return False

        package_manager.install_packages(to_install)
    elif failed_checks:
        print "Failed checks\n"
        _print_checks(failed_checks)

        if to_install:
            print "\nYou might try to install the following packages\n"
            print " ".join(to_install)

        return False

    return True

def remove_packages(package_manager, packages):
    distro_name = distro.get_distro_info().name

    to_keep = []
    for package_info in packages.values():
        if distro_name in package_info:
            for package in package_info[distro_name]:
                if package not in to_keep:
                    to_keep.append(package)

    try:
        to_keep = package_manager.find_with_deps(to_keep)
    except NotImplementedError:
        return

    all = package_manager.find_all()

    to_remove = []
    for package in all:
        if package not in to_keep:
            to_remove.append(package)

    if to_remove:
        package_manager.remove_packages(to_remove)

def check(remove=False, update=False, test=False, interactive=True,
          skip_if_unchanged=False):
    if skip_if_unchanged:
        if config.get_commit_id() == state.get_last_system_check():
            return

    package_manager = \
        distro.get_package_manager(test=test, interactive=interactive)

    distro_name = distro.get_distro_info().name
    packages = config.load_packages()

    checks = config.load_prerequisites()
    if not run_checks(package_manager, checks, packages):
        sys.exit(1)

    xvfb_proc, orig_display = xvfb.start()

    if not run_checks(package_manager, config.load_checks(), packages):
        sys.exit(1)

    xvfb.stop(xvfb_proc, orig_display)

    print "All the required dependencies are installed."

    if update:
        package_manager.update()

    if remove:
        remove_packages(package_manager, packages)

    state.touch_last_system_check()
