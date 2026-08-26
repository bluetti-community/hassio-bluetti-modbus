# hassio-bluetti-modbus

Unofficial Bluetti Modbus Integration for Home Assistant

## Disclaimer
This integration is provided without any warranty or support by Bluetti. I do not take responsibility for any problems it may cause in all cases. Use it at your own risk.

## Supported devices

- Balco260
- EP2000
- SMeter (untested against real hardware so far)

You have to enable Modbus TCP in your device's web interface first. Field
names and available data come from
[bluetti-modbus-lib](https://github.com/bluetti-community/bluetti-modbus-lib), which
this integration depends on. This integration currently only reads data
(sensors) - it does not yet expose any switches or other controls, even for
registers the library marks as writable.

Note: `requirements` currently points `bluetti-modbus-lib` at this fork's
GitHub repo directly rather than PyPI, since the PyPI project of that name
is still Patrick762's original, unmaintained package. This is a temporary
arrangement until a proper release under `bluetti-community` (or a renamed
package) is set up.

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

## Affiliate links (Anzeige / Ad)

If you want to support this project and buy a Bluetti device, you can use the following affiliate links:

- <a href="https://tidd.ly/4xJPHDn" target="_blank" rel="sponsored">Balco 260</a>

> [!NOTE]
> DE: Bei diesem Link handelt es sich um einen Affiliate-Link. Wenn du darüber kaufst, erhalte ich eine kleine Provision. Für dich entstehen keine Zusatzkosten.
>
> EN: This is an affiliate link. If you make a purchase through it, I may earn a small commission at no extra cost to you.
