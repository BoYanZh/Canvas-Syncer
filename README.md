# Canvas-Syncer

[![MIT License](https://img.shields.io/pypi/l/canvassyncer)](https://github.com/BoYanZh/Canvas-Syncer/blob/master/LICENSE)
[![CodeFactor](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer/badge)](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer)
[![PyPi Version](https://img.shields.io/pypi/v/canvassyncer)](https://pypi.org/pypi/canvassyncer)

An async python script that synchronizes files and folders across Canvas Files and local, with extremely fast speed.

## Installation

You may use one of the following

### Through Binary

For Windows users, you can find binary(.exe) file here: <https://github.com/BoYanZh/Canvas-Syncer/releases>. Unzip it and double click `canvassyncer.exe` file to run, or calling it in shell.

### Through `pip`

```bash
pip3 install -U canvassyncer
```

If you have not installed `pip` yet, you may refer to <https://pip.pypa.io/en/stable/installing/> or the search engine to get your `pip`.

### From Source

```bash
git clone https://github.com/BoYanZh/Canvas-Syncer && cd Canvas-Syncer
pip install -e .
```

## Usage

```bash
canvassyncer
```

Then input the information following the guide.

*Note:*
1. `courseCode` should be something like `VG100`, `ECE4530J`
2. `courseID` should be an integer. Check the canvas link of the course. e.g. `courseID = 7` for <https://umjicanvas.com/courses/7>.

You can use `canvassyncer -h` to get help.

Optional arguments:

```text
  -h, --help            show this help message and exit
  -r                    recreate config file
  -y                    confirm all prompts
  --no-subfolder        do not create a course code named subfolder when synchronizing files
  -p PATH, --path PATH  appoint config file path
  -c CONNECTION, --connection CONNECTION
                        max connection count with server
  -x PROXY, --proxy PROXY
                        download proxy
  -V, --version         show program's version number and exit
  -d, --debug           show debug information
  --no-keep-older-version
                        do not keep older version
```

### How to get your token?

Open Your Canvas-Account-Approved Integrations-New Access Token

Or it can be easily achieved with <https://github.com/BoYanZh/JI-Auth> if you are a UM-SJTU-JI student.


## Contribution

Please feel free to create issues and pull requests.
