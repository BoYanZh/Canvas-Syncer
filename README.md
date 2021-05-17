# Canvas-Syncer

[![MIT License](https://img.shields.io/pypi/l/canvassyncer)](https://github.com/BoYanZh/Canvas-Syncer/blob/master/LICENSE)
[![CodeFactor](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer/badge)](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer)
[![PyPi Version](https://img.shields.io/pypi/v/canvassyncer)](https://pypi.org/pypi/canvassyncer)
[![PyPi Downloads](https://pepy.tech/badge/canvassyncer)](https://pepy.tech/project/canvassyncer)

A async python script that sync files and folders across Canvas Files and local, with extremely fast speed.

## Usage

### Through Binary

For Windows users, you can find binary(.exe) file here: <https://github.com/BoYanZh/Canvas-Syncer/releases>. Double click to run.

### Through `pip`

```bash
pip3 install canvassyncer
canvassyncer
```

Then input the information following the guide.

*Note:*
1. `courseCode` should be something like `VG100`, `VG101`
2. `courseID` should be an integer. Check the canvas link of the course. e.g. `courseID = 7` for <https://umjicanvas.com/courses/7>.


If you have not installed `pip` yet, you may refer to <https://pip.pypa.io/en/stable/installing/> or the search engine to get your `pip`.

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
```

### How to get your token?

Open Your Canvas-Account-Approved Integrations-New Access Token

You may also refer to <https://github.com/tc-imba/canvas-auto-rubric#generate-key-access-token-on-canvas>.

## Contribution

Please feel free to create issues and pull requests.
