import logging
import os
from datetime import date
import argparse
import yaml
import sys

from pkg_resources import resource_filename

INPUT_DIR_KEY = "input_dir"
OUTPUT_DIR_KEY = "output_dir"
WORK_DIR_KEY = "work_dir"


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
        ssh.connect('0.0.0.0', port=22, username=remote_username, password=remote_password)

        # Define progress callback that prints the current percentage completed for the file
        logging.info("Fetching: " + source + " to " + dest)

        def progress(filename, size, sent):
            last_message = "Receiving: {0} progress: {1}".format(str(filename),
                                                                 round(float(sent) / float(size) * 100.0), 5)
            logging.debug(last_message)

        # SCPCLient takes a paramiko transport and progress callback as its arguments.
        scp = SCPClient(ssh.get_transport(), progress=progress)

        scp.get(source.split(":")[1], dest, recursive=True)
        # Should now be printing the current progress of your put function.
        scp.close()


def _copy_file_locally(source, dest):
    from distutils.dir_util import copy_tree
    copy_tree(source, dest)


def _is_local_file(source):
    return not str(source).__contains__(":")


def perform_sync(config_file=None):
    if config_file is None:
        args = parse_args("perform_sync")
        config_file = args.config_file

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

    if "local_data" in dir_configs.keys():
        local_data_dir = os.path.join(work_dir, "data")
    else:
        local_data_dir = dir_configs[WORK_DIR_KEY]

    if os.path.exists(os.path.join(work_dir, "last_update.txt")):
        with open(os.path.join(work_dir, "last_update.txt"), "r") as last_file:
            last_update = last_file.read()
    else:
        last_update = 0

    if "use_gateway" in configs.keys():
        use_gateway = configs["use_gateway"]
        assert (configs["use_gateway"] and "gateway" in configs["hosts"].keys()) or (
            not configs["use_gateway"]), "Must specify gateway host to use gateway."

        gateway_configs = configs["hosts"]["gateway"]
        assert "location" in gateway_configs.keys() and gateway_configs["location"] != "", "Must specify gateway location"
        assert "username" in gateway_configs.keys() and gateway_configs["username"] != "", "Must specify gateway username"
        assert "password" in gateway_configs.keys() and gateway_configs["password"] != "", "Must specify gateway password"

        gateway_username = gateway_configs["username"]
        gateway_password = gateway_configs["password"]
        gateway_location = gateway_configs["location"]
    else:
        use_gateway = False
        gateway_username = None
        gateway_password = None
        gateway_location = None



    logging.info("Creating directories.")
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(local_data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    current_time = _current_day_seconds()
    should_refresh_files = False

    if data_refresh_mode == "always":
        should_refresh_files = True
        logging.info("always downloading new data.")
    elif _seconds_to_days(current_time - int(last_update)) >= data_refresh_time:
        should_refresh_files = True
        logging.info("data may be stale, downloading new version.")
    elif data_refresh_mode == "auto" and not os.path.exists(local_data_dir) or len(os.listdir(local_data_dir)) == 0:
        should_refresh_files = True
        logging.info("data_refresh_mode is Auto, downloading new files.")

    if should_refresh_files and use_gateway and not _is_local_file(input_dir):
        logging.info("Copying files through gateway.")

        # Get remote location...
        remote_host_name = input_dir.split(":")[0]
        assert remote_host_name in configs["hosts"], "Unknown host.  Must specify in configs[`hosts`]"

        remote_configs = configs["hosts"][remote_host_name]
        assert "location" in remote_configs.keys() and remote_configs["location"] != "", "Must specify remote location"
        assert "username" in remote_configs.keys() and remote_configs["username"] != "", "Must specify remote username"
        assert "password" in remote_configs.keys() and remote_configs["password"] != "", "Must specify remote password"

        remote_username = remote_configs["username"]
        remote_password = remote_configs["password"]
        remote_location = remote_configs["location"]

        _fetch_files_gateway(input_dir, local_data_dir,
                             gateway_location, gateway_username, gateway_password,
                             remote_location, remote_username, remote_password)

    elif should_refresh_files and not _is_local_file(input_dir):
        logging.info("Copying files from server.")

        remote_host_name = input_dir.split(":")[0]
        assert remote_host_name in configs["hosts"] and configs["hosts"][remote_host_name] != "", "Unknown host.  Must specify in configs[`hosts`]"

        remote_configs = configs["hosts"][remote_host_name]
        assert "username" in remote_configs.keys() and remote_configs["username"] != "", "Must specify remote username"
        assert "password" in remote_configs.keys() and remote_configs["password"] != "", "Must specify remote password"

        remote_username = remote_configs["username"]
        remote_password = remote_configs["password"]

        _fetch_files(input_dir, local_data_dir, remote_username, remote_password)

    elif should_refresh_files and _is_local_file(input_dir):
        logging.info("Copying local files.")
        _copy_file_locally(input_dir, output_dir)

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


def create_r_project(work_dir="", project_name=None, output_format=None, output_dir="", input_dir="", use_gateway=False):
    output_format_choices = ["pdf_output", "word_output", "html_output"]
    if work_dir is None or project_name is None or output_format is None:
        args = parse_args("create_r_project")

        work_dir = args.work_dir
        output_dir = args.output_dir
        input_dir = args.input_dir
        use_gateway = args.use_gateway
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
            os.makedirs(os.path.join(dir_to_create_project, dir_to_make))

    default_yaml_schema = {
        "project_name": project_name,
        "dir": {
            WORK_DIR_KEY: work_dir,
            INPUT_DIR_KEY: input_dir,
            OUTPUT_DIR_KEY: output_dir,
        },
        "data_refresh_mode": "auto",
        "data_refresh_days": 30,
        "local_data": os.path.join(work_dir, "local_data"),
        "use_gateway": use_gateway,
        "hosts": {
            "gateway": {
                "location": "",
                "username": "",
                "password": ""
            }
        }
    }

    update_yaml_config(os.path.join(dir_to_create_project, "config.yml"), default_yaml_schema)

    default_r_lines = []
    with open(resource_filename("r_utils", "blank_rmd"), "r") as default_r_mkdown:
        for line in default_r_mkdown:
            default_r_lines.append(line.strip())

    default_r = "\n".join(default_r_lines)

    with open(os.path.join(dir_to_create_project, "reports", "README.rmd"), "w") as r_mkdown:
        username = get_username()

        r_mkdown.write(default_r.format(dir_to_create_project, username, date.today(), output_format,
                                        **{"r setup, include=FALSE": "{r setup, include=FALSE}",
                                           "r cars": "{r cars}",
                                           "r pressure, echo=FALSE": "{r pressure, echo=FALSE}"}))

    print("Created Project")


if __name__ == "__main__":
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)s]')
    ch.setFormatter(formatter)
    root.addHandler(ch)

    create_r_project("/tmp", "test", output_format="pdf_output")
    perform_sync("/tmp/test/config.yml")
