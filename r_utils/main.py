import logging
import os
from datetime import date
import argparse
from getpass import getpass

import yaml
import sys

from pkg_resources import resource_filename

INPUT_DIR_KEY = "input_dir"
OUTPUT_DIR_KEY = "output_dir"
WORK_DIR_KEY = "work_dir"


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)s]')
    ch.setFormatter(formatter)
    root.addHandler(ch)

def _current_day_seconds():
    import time
    return int(time.time())


def _seconds_to_days(x):
    return float(x) / float(3600 * 24)


def get_username():
    import getpass
    username = getpass.getuser()
    return username


def is_valid_file(file):
    try:
        with open(file, "r") as yaml_file:
            return os.path.exists(file) \
                   and (str(file).endswith(".yml") or str(file).endswith(".yaml")) \
                   and yaml.load(yaml_file) is not None
    except IOError:
        return False


def _read_configs(file):
    import yaml

    assert is_valid_file(file), "File must exist and must be a valid yaml file."
    with open(file, "r") as yaml_file:
        return yaml.load(yaml_file)


def _fetch_files(source, dest, remote_username, remote_password):
    import paramiko
    from scp import SCPClient

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    logging.debug("Connecting using: " + remote_username + " " + remote_password)
    ssh.connect('0.0.0.0', port=10022, username=remote_username, password=remote_password)

    # Define progress callback that prints the current percentage completed for the file
    logging.info("Fetching: " + source + " to " + dest)
    def progress(filename, size, sent):
        last_message = "Receiving: {0} progress: {1}".format(str(filename), round(float(sent) / float(size) * 100.0), 5)
        logging.debug(last_message)

    # SCPCLient takes a paramiko transport and progress callback as its arguments.
    scp = SCPClient(ssh.get_transport(), progress=progress)

    scp.get(source.split(":")[1], dest, recursive=True)
    # Should now be printing the current progress of your put function.
    scp.close()


def _fetch_files_gateway(source, dest,
                         gateway_location, gateway_username, gateway_password,
                         remote_location, remote_username, remote_password):

    from sshtunnel import SSHTunnelForwarder

    with SSHTunnelForwarder(
            (gateway_location, 22),
            ssh_username=gateway_username,
            ssh_password=gateway_password,
            remote_bind_address=(remote_location, 22),
            local_bind_address=('0.0.0.0', 10022)
    ) as tunnel:
        import paramiko
        from scp import SCPClient

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        logging.debug("Connecting using: " + gateway_location + " " + remote_username + " " + remote_password + " -> " + remote_location)
        ssh.connect('0.0.0.0', port=10022, username=remote_username, password=remote_password)

        # Define progress callback that prints the current percentage completed for the file
        logging.info("Fetching: " + source + " to " + dest)

        def progress(filename, size, sent):
            last_message = "Receiving: {0}:{1} progress: {2}".format(str(source), str(dest), round(float(sent) / float(size) * 100.0), 5)
            logging.debug(last_message)

        # SCPCLient takes a paramiko transport and progress callback as its arguments.
        scp = SCPClient(ssh.get_transport(), progress=progress)

        scp.get(source.split(":")[1], dest, recursive=True)
        # Should now be printing the current progress of your put function.
        scp.close()


def _copy_file_locally(source, dest):
    from distutils.dir_util import copy_tree
    import shutil

    if os.path.isdir(source):
        copy_tree(source, dest)
    else:
        shutil.copy2(source, dest)


def _is_local_file(source):
    return not str(source).__contains__(":")


def perform_sync(config_file=None):
    setup_logging()
    if config_file is None:
        args = parse_args("perform_sync")
        config_file = args.config_file
    if (config_file is None or config_file == "") and os.path.exists("config.yml"):
        config_file = "config.yml"

    configs, data_refresh_mode, data_refresh_time, input_dir, last_update, local_data_dir, output_dir, work_dir = verify_configs(config_file)

    hosts = {}

    # Get remote location...
    if type(input_dir) is list:
        for input_d in input_dir:
            assert input_d != "", "Must specify an input directory."
            if not _is_local_file(input_d):
                remote_host_name = input_d.split(":")[0]
                assert remote_host_name in configs["hosts"], "Unknown host.  Must specify in configs[`hosts`]"
                if remote_host_name in hosts:
                    logging.info("Already processed host, skipping.")
                else:
                    hosts.update({remote_host_name: configs["hosts"][remote_host_name]})
    else:
        assert input_dir != "", "Must specify an input directory."
        if not _is_local_file(input_dir):
            remote_host_name = input_dir.split(":")[0]
            assert remote_host_name in configs["hosts"].keys(), "Unknown host.  Must specify in configs[`hosts`]"

    for remote_host_name, remote_configs in hosts.items():
        assert "location" in remote_configs.keys() and remote_configs["location"] != "", "Must specify remote location"
        assert "username" in remote_configs.keys() and remote_configs["username"] != "", "Must specify remote username"

        remote_username = remote_configs["username"]
        remote_location = remote_configs["location"]

        if "password" in remote_configs.keys() and remote_configs["password"] != "":
            remote_password = remote_configs["password"]
        else:
            remote_password = getpass(prompt="Enter your password for ({0}): ".format(remote_location))

        if "use_gateway" in remote_configs.keys():
            gateway_to_use = remote_configs["use_gateway"]
            assert (gateway_to_use in configs["hosts"].keys()), "Must specify gateway host to use gateway."

            gateway_configs = configs["hosts"][gateway_to_use]
            assert "location" in gateway_configs.keys() and gateway_configs["location"] != "", "Must specify gateway location"
            gateway_location = gateway_configs["location"]

            if "username" in gateway_configs.keys() and gateway_configs["username"] != "":
                gateway_username = gateway_configs["username"]
            else:
                logging.info("Using same username for gateway and remote.")
                gateway_username = remote_username

            if "password" in gateway_configs.keys() and gateway_configs["password"] != "":
                gateway_password = gateway_configs["password"]
            else:
                logging.info("Using same password for gateway and remote.")
                gateway_password = remote_password

            hosts.update(
                    {remote_host_name: {
                        "username":    remote_username,
                        "location":    remote_location,
                        "password":    remote_password,
                        "use_gateway": True,
                        "gateway": {
                            "location": gateway_location,
                            "username": gateway_username,
                            "password": gateway_password
                        }
                    }
                })

        else:
            hosts.update({remote_host_name: {
                "username": remote_username,
                "location": remote_location,
                "password": remote_password,
                "use_gateway": False
            }})

    current_time = _current_day_seconds()
    should_refresh_files = False

    logging.info("Creating directories.")
    os.makedirs(work_dir, exist_ok=True)
    if type(input_dir) is list:
        for input_d in input_dir:
            if _is_local_file(input_d) and not os.path.exists(input_d):
                os.makedirs(input_d, exist_ok=True)
    elif _is_local_file(input_dir) and not os.path.exists(input_dir):
        os.makedirs(input_dir)
    os.makedirs(output_dir, exist_ok=True)

    logging.debug("Input: {0} Output: {1} LocalData: {2} Workdir: {3}".format(input_dir, output_dir, local_data_dir, work_dir))
    if data_refresh_mode == "always":
        should_refresh_files = True
        logging.info("always downloading new data.")
    elif _seconds_to_days(current_time - int(last_update)) >= data_refresh_time:
        should_refresh_files = True
        logging.info("data may be stale, downloading new version.")
    elif data_refresh_mode == "auto" and not os.path.exists(local_data_dir) or len(os.listdir(local_data_dir)) == 0:
        should_refresh_files = True
        logging.info("data_refresh_mode is Auto, downloading new files.")

    if type(input_dir) is list:
        for input_d in input_dir:
            sync_input_dir(configs, hosts, input_d, local_data_dir, output_dir, should_refresh_files, work_dir)
    else:
        sync_input_dir(configs, hosts, input_dir, local_data_dir, output_dir, should_refresh_files, work_dir)


def sync_input_dir(configs, hosts, input_dir, local_data_dir, output_dir, should_refresh_files, work_dir):
    if not _is_local_file(input_dir):
        remote_host_name = input_dir.split(":")[0]
        use_gateway = hosts[remote_host_name]["use_gateway"]
        if use_gateway:
            gateway_location = hosts[remote_host_name]["gateway"]["location"]
            gateway_username = hosts[remote_host_name]["gateway"]["username"]
            gateway_password = hosts[remote_host_name]["gateway"]["password"]
        else:
            gateway_location = gateway_username = gateway_password = None
        remote_location = hosts[remote_host_name]["location"]
        remote_username = hosts[remote_host_name]["username"]
        remote_password = hosts[remote_host_name]["password"]

        sync_input_folder(should_refresh_files, use_gateway, input_dir, local_data_dir, output_dir, work_dir,
                          gateway_location, gateway_username, gateway_password,
                          remote_location, remote_username, remote_password, configs["hosts"])
    else:
        sync_input_folder(should_refresh_files, False, input_dir, local_data_dir, output_dir, work_dir,
                          None, None, None, None, None, None, None)

def verify_configs(config_file):
    configs = _read_configs(config_file)
    assert "dir" in configs.keys(), "'dir' must be a key in config file."
    dir_configs = configs["dir"]
    assert INPUT_DIR_KEY in dir_configs.keys(), "'{0}' must be a key in config file".format(INPUT_DIR_KEY)
    assert OUTPUT_DIR_KEY in dir_configs.keys(), "'{0}' must be a key in config file".format(OUTPUT_DIR_KEY)
    assert WORK_DIR_KEY in dir_configs.keys(), "'{0}' must be a key in config file".format(WORK_DIR_KEY)
    if "data_refresh_mode" in configs.keys():
        data_refresh_mode = configs["data_refresh_mode"]
    else:
        data_refresh_mode = "auto"
    assert data_refresh_mode in ["auto", "always", "manual"], \
        "`data_refresh_mode` must be one of [auto, always, manual]"
    if "data_refresh_days" in configs.keys():
        data_refresh_time = configs["data_refresh_days"]
    else:
        data_refresh_time = 0
    input_dir = dir_configs[INPUT_DIR_KEY]
    work_dir = dir_configs[WORK_DIR_KEY]
    output_dir = dir_configs[OUTPUT_DIR_KEY]
    local_data_dir = os.path.join(work_dir, "data")

    assert input_dir != "" or (type(input_dir) == list and len(input_dir) > 0), "Must specify an input directory."
    assert output_dir != "", "Must specify an output directory."
    assert work_dir != "", "Must specify an working directory."

    if os.path.exists(os.path.join(work_dir, "last_update.txt")):
        with open(os.path.join(work_dir, "last_update.txt"), "r") as last_file:
            last_update = last_file.read()
    else:
        last_update = 0
    return configs, data_refresh_mode, data_refresh_time, input_dir, last_update, local_data_dir, output_dir, work_dir


def sync_input_folder(should_refresh_files, use_gateway, input_dir, local_data_dir, output_dir, work_dir,
                      gateway_location, gateway_username, gateway_password,
                      remote_location, remote_username, remote_password, hosts):

    if should_refresh_files and use_gateway and not _is_local_file(input_dir):
        logging.info("Copying files through gateway.")

        _fetch_files_gateway(input_dir, local_data_dir,
                             gateway_location, gateway_username, gateway_password,
                             remote_location, remote_username, remote_password)

    elif should_refresh_files and not _is_local_file(input_dir):
        logging.info("Copying files from server.")

        remote_host_name = input_dir.split(":")[0]
        assert remote_host_name in hosts and hosts[remote_host_name] != "", "Unknown host.  Must specify in configs[`hosts`]"

        remote_configs = hosts[remote_host_name]
        assert "username" in remote_configs.keys() and remote_configs["username"] != "", "Must specify remote username"
        assert "password" in remote_configs.keys() and remote_configs["password"] != "", "Must specify remote password"

        remote_username = remote_configs["username"]
        remote_password = remote_configs["password"]

        _fetch_files(input_dir, local_data_dir, remote_username, remote_password)

    elif should_refresh_files and _is_local_file(input_dir):
        logging.info("Copying local files: {0}, {1}".format(input_dir, local_data_dir))
        assert os.path.exists(input_dir), "File not found: ".format(input_dir)
        _copy_file_locally(input_dir, local_data_dir)

    else:
        logging.info("Using local data files, not attempting download.")

    with open(os.path.join(work_dir, "last_update.txt"), "w") as last_file:
        last_file.write(str(_current_day_seconds()))

    logging.info("Finished fetching files.")


def update_yaml_config(config_file, data):
    with open(config_file, "w") as default_yaml:
        yaml.dump(data, default_yaml, default_flow_style=False)


def parse_args(root_key):
    parser = argparse.ArgumentParser()
    with open(resource_filename("r_utils", "argparse.yaml"), "r") as yaml_default:
        parse_configs = yaml.load(yaml_default)

        for cmd, value in parse_configs[root_key].items():
            parser.add_argument("--" + cmd, dest=cmd, **value)

        args = parser.parse_args()
        return args


def create_r_project(work_dir="", project_name=None, output_format=None, output_dir="", input_dir=""):
    setup_logging()
    output_format_choices = ["pdf_output", "word_output", "html_output"]
    if work_dir is None or project_name is None or output_format is None:
        args = parse_args("create_r_project")

        work_dir = args.work_dir
        output_dir = args.output_dir
        input_dir = args.input_dir
        project_name = args.project_name
        output_format = args.output_format

    assert output_format in output_format_choices, "output_format must be one of " + ",".join(output_format_choices)

    if os.getcwd().split("/")[-1] == project_name:
        dir_to_create_project = ""
    else:
        dir_to_create_project = project_name

    directories_to_make = ["src", "reports"]

    for dir_to_make in directories_to_make:
        if not os.path.exists(os.path.join(dir_to_create_project, dir_to_make)):
            os.makedirs(os.path.join(dir_to_create_project, dir_to_make), exist_ok=True)

    default_yaml_schema = {
        "project_name": project_name,
        "dir": {
            WORK_DIR_KEY: work_dir,
            INPUT_DIR_KEY: input_dir,
            OUTPUT_DIR_KEY: output_dir,
        },
        "data_refresh_mode": "auto",
        "data_refresh_days": 30,
        #"local_data": os.path.join(work_dir, "local_data"),
        "hosts": {
            "gateway": {
                "location": "",
                "username": "",
                "password": "",
            },
            "host1": {
                "location": "",
                "username": "",
                "password": "",
                "use_gateway": "gateway"
            }
        }
    }

    logging.info("Creating: " + os.path.join(dir_to_create_project, "config.yml"))
    update_yaml_config(os.path.join(dir_to_create_project, "config.yml"), default_yaml_schema)

    default_r_lines = []
    with open(resource_filename("r_utils", "blank_rmd"), "r") as default_r_mkdown:
        for line in default_r_mkdown:
            default_r_lines.append(line.strip())

    default_r = "\n".join(default_r_lines)

    with open(os.path.join(dir_to_create_project, "reports", "README.rmd"), "w") as r_mkdown:
        logging.info("Creating: " + os.path.join(dir_to_create_project, "reports", "README.rmd"))
        username = get_username()

        r_mkdown.write(default_r.format(dir_to_create_project, username, date.today(), output_format,
                                        **{"r setup, include=FALSE": "{r setup, include=FALSE}",
                                           "r cars": "{r cars}",
                                           "r pressure, echo=FALSE": "{r pressure, echo=FALSE}"}))

    logging.info("Created Project")


if __name__ == "__main__":
    #create_r_project("/tmp", "test", output_format="pdf_output")
    perform_sync("test/config.yml")
