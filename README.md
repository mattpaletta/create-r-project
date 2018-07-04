# create-r-project

# Installation
`pip install git+https://github.com/mattpaletta/create-r-project.git`

# Usage
There are 2 scripts that will be installed:
## create-r-project
This will create a new R project in your current directory along with a default configuration file.

# Parameters
project_name: "Specifies the project name.  If you are in the project directory already, folders & files will be created here."

For more information, see `create-r-project --help`

## sync-project
This will sync the project with any remote files you may be trying to access locally.

# Parameters
`project_name`: Specifies the project name.
`dir`: Specifies the working directory (temporary & intermediate files), input directory (remote or local data source) [as a list or a string], and an output directory (for final outputs)
`data_refresh_mode`: 
* manual: the user will manually sync files
* auto: files will be updated if the last update occured more than `data_refresh_days` ago, or if no local files exist (like the first time you run the project)
* always: files will be updated every time this script is called.  The `last_update` date will be updated.
`data_refresh_days`: If `data_refresh_mode` is set to `auto`, specifies how long to keep the current data before downloading new versions from the server.
`local_data`: The local directory to store downloaded data.  Default `<work_dir>/local_data>`.
`hosts`: Specifies information about any hosts you want to be able to connect to. You must specify a location (hostname/IP) of the remote machine, and a username.  Password is optional.  If you do not specify a password, you will be prompted for one at runtime, once per host.  If you specify `use_gateway=<my_gateway>`, you must specify a `<my_gateway>` under `hosts`.  You cannot currently push files to the server after the script completes, only pulling data locally.  If you want to see this added, make a feature request.
	* use_gateway: location (hostname/IP), username and password for the gateway machine.  Currently only supports 1 gateway.  If you want more, make a feature request.
* other: location (hostname/IP), username and password for any remote machines.  The `key` must match the prefix of remote files/folders.  i.e. `baz:~/my_file.dat` where `baz` is the key under `hosts`.

For more information, see `sync-project --help`

### Example Gateway usage:
For this example, assume the following conditions:
- Our username is `bar`
- Our project is called `proj` located at `~/Projects/proj` 
- We have access to a machine `Foo.ca` over ssh
- From `Foo.ca` we have access to a machine `Baz.ca`
- On `Baz.ca`, we want to use the file `~/my_file.dat`
- our login credientials for `Foo.ca` are `u=bar, p=abcd`
- our login credientials for `baz.ca` are `u=bar, p=1234`
- we are currently in `~/Projects/proj` (our project directory)

In our config file (config.yml), we would update it to the following:
```
"project_name": "proj",
"dir": {
	WORK_DIR_KEY: "~/Projects/proj/tmp,
	INPUT_DIR_KEY: "baz:~/my_file.dat",
	OUTPUT_DIR_KEY: ~/Projects/proj/outputs,
},
"data_refresh_mode": "auto",
"data_refresh_days": 30,
"hosts": {
	"gateway": {
		"location": "Foo.ca",
		"username": "bar",
		"password": "abcd"
	},
	"baz": {
		"location" "baz.ca",
		"username": "bar",
		"password": "1234",
		"use_gateway": "gateway"
	}
}
```

The script will use these credientials to copy `baz:~/my_file.dat` to `~/Projects/proj/tmp/local_data/my_file.dat`, which our program can then read from.

### Questions, Comments, Concerns, Queries, Qwibbles?

If you have any questions, comments, or concerns please leave them in the GitHub
Issues tracker:

https://github.com/mattpaletta/optional-thrift/issues

### Bug reports

If you discover any bugs, feel free to create an issue on GitHub. Please add as much information as
possible to help us fixing the possible bug. We also encourage you to help even more by forking and
sending us a pull request.

https://github.com/mattpaletta/create-r-project/issues

## Maintainers

* Matthew Paletta (https://github.com/mattpaletta)

## License

MIT License. Copyright 2018 Matthew Paletta. http://mrated.ca
