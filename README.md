# hassio-bluetti-modbus

[![HACS Custom][hacs-shield]][hacs]
[![Release][release-shield]][release]
[![License][license-shield]](LICENSE)
[![Tests][tests-shield]][tests]
[![HACS Validation][hacs-validation-shield]][hacs-validation]

Bluetti Modbus Integration for Home Assistant

## Disclaimer
This integration is provided without any warranty or support by Bluetti. I do not take responsibility for any problems it may cause in all cases. Use it at your own risk.

## Supported devices

- Balco 260
- S Meter

EP2000 support was pulled pending confirmation that it actually exposes
Modbus TCP at all - see
[bluetti-official/bluetti-home-assistant#125](https://github.com/bluetti-official/bluetti-home-assistant/issues/125).

You have to enable Modbus TCP in your device's web interface first. Field
names and available data come from
[bluetti-community/bluetti-modbus](https://github.com/bluetti-community/bluetti-modbus)
(published on PyPI as `bluetti-modbus`). Most fields are read-only sensors;
Balco 260's two SOC thresholds (min discharge / max charge limit) are
exposed as writable number entities, and its 3 control switches (AC output,
grid charging, grid feed-in) as switch entities.

Note: this integration bundles its own copy of that library
(`custom_components/bluetti_modbus/vendor/`) rather than depending on it via
PyPI directly. Run `scripts/vendor_bluetti_modbus_lib.sh` to pick up a newer
version.

## Installation

### Via HACS

1. Add this repository as a HACS custom repository (HACS -> Integrations ->
   the "..." menu in the top right -> Custom repositories), category
   "Integration".
2. Find "Bluetti Modbus" in HACS and install it.
3. Restart Home Assistant.
4. Go to Settings -> Devices & services -> Add Integration -> "Bluetti
   Modbus", and enter your device's IP address, port (502 by default), and
   type.

### Manually

1. Copy `custom_components/bluetti_modbus` into your Home Assistant
   configuration's `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration the same way as above (Settings -> Devices &
   services -> Add Integration -> "Bluetti Modbus").

## Testing

The test suite (100% coverage enforced) runs automatically in CI on every
pull request. To run it locally without installing anything but Docker:

```bash
./test.sh
```

This builds `Dockerfile.test` and runs the same `coverage run` /
`coverage report --fail-under=100` steps CI does.

## Relationship to Patrick762's `hassio-bluetti-modbus`

This repository started as a fork of
[Patrick762/hassio-bluetti-modbus](https://github.com/Patrick762/hassio-bluetti-modbus)
and has since diverged significantly (coordinator/entity handling, retry
handling, multi-pack support, device coverage). Patrick762 is still actively
maintaining his own version independently.

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[release-shield]: https://img.shields.io/github/v/release/bluetti-community/hassio-bluetti-modbus.svg
[release]: https://github.com/bluetti-community/hassio-bluetti-modbus/releases
[license-shield]: https://img.shields.io/github/license/bluetti-community/hassio-bluetti-modbus.svg
[tests-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml/badge.svg
[tests]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml
[hacs-validation-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml/badge.svg
[hacs-validation]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml
