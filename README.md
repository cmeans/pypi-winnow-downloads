# pypi-winnow-downloads

[![PyPI version](https://img.shields.io/pypi/v/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![Python versions](https://img.shields.io/pypi/pyversions/pypi-winnow-downloads)](https://pypi.org/project/pypi-winnow-downloads/)
[![License](https://img.shields.io/pypi/l/pypi-winnow-downloads)](https://github.com/cmeans/pypi-winnow-downloads/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/cmeans/pypi-winnow-downloads/ci.yml?label=CI)](https://github.com/cmeans/pypi-winnow-downloads/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/cmeans/pypi-winnow-downloads/graph/badge.svg)](https://codecov.io/gh/cmeans/pypi-winnow-downloads)
[![non-CI downloads](https://img.shields.io/endpoint?url=https%3A%2F%2Fpypi-badges.intfar.com%2Fpypi-winnow-downloads%2Fdownloads-30d.json)](https://pypi.org/project/pypi-winnow-downloads/)

Self-hosted PyPI download badge service that winnows CI traffic out of download
counts. Produces [shields.io](https://shields.io/endpoint)-compatible endpoint
badges filtered by BigQuery's `details.ci` field — more honest than any existing
alternative for small or young Python packages.

> The "non-CI downloads" badge above is served by this project itself —
> eating our own dogfood. The endpoint goes live when the deployment
> ships (milestone M3); until then shields.io renders an error state,
> which is the correct signal for a pre-v1 project.

Pre-alpha. Not yet usable.
