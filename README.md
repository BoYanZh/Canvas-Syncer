# Canvas-Syncer

[![MIT License](https://img.shields.io/apm/l/atomic-design-ui.svg?)](https://github.com/tterb/atomic-design-ui/blob/master/LICENSEs)
[![CodeFactor](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer/badge)](https://www.codefactor.io/repository/github/boyanzh/canvas-syncer)
[![PyPi Version](https://img.shields.io/pypi/v/canvassyncer.svg)](https://pypi.org/pypi/canvassyncer)

A async python script that sync files and folders across Canvas Files and local, with extremely fast speed.

## Usage

```bash
pip3 install canvassyncer
canvassyncer
```

Then input the information following the guide.

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

You may also refer to <https://github.com/tc-imba/canvas-auto-rubric#generate-key-access-token-on-canvas>

## Contribution

Please feel free to create issues and pull requests.
