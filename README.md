# BaNaNaS Server

[![GitHub License](https://img.shields.io/github/license/OpenTTD/bananas-server)](https://github.com/OpenTTD/bananas-server/blob/main/LICENSE)

This is the server serving the in-game client for OpenTTD's content service, called BaNaNaS.
It works together with [bananas-api](https://github.com/OpenTTD/bananas-api), which serves the HTTP API.

See [introduction.md](https://github.com/OpenTTD/bananas-api/tree/main/docs/introduction.md) for more documentation about the different BaNaNaS components and how they work together.

## Development

This API is written in Python 3.11 with aiohttp, and makes strong use of asyncio.

### Running a local server

#### Dependencies

- Python3.11 or higher.

#### Preparing your venv

To start it, you are advised to first create a virtualenv:

```bash
python3 -m venv .env
.env/bin/pip install -r requirements.txt
```

#### Starting a local server

Next, you can start the HTTP server by running:

```bash
.env/bin/python -m bananas_server --web-port 8081 --storage local --index local
```

This will start the HTTP part of this server on port 8081 and the content server part on port 3978 for you to work with locally.
You will either have to modify the client to use `localhost` as content server, or change your `hosts` file to change the IP of `binaries.openttd.org` and `content.openttd.org` to point to `127.0.0.1`.

### Running via docker

```bash
docker build -t openttd/bananas-server:local .
export BANANAS_COMMON=$(pwd)/../bananas-common
mkdir -p "${BANANAS_COMMON}/local_storage" "${BANANAS_COMMON}/BaNaNaS"
docker run --rm -p 127.0.0.1:8081:80 -p 127.0.0.1:3978:3978 -v "${BANANAS_COMMON}/local_storage:/code/local_storage" -v "${BANANAS_COMMON}/BaNaNaS:/code/BaNaNaS" openttd/bananas-server:local
```

The mount assumes that [bananas-api](https://github.com/OpenTTD/bananas-api) and this repository has the same parent folder on your disk, as both servers need to read the same local storage.
