# Bluetti Modbus for Home Assistant

[![HACS Custom][hacs-shield]][hacs]
[![Release][release-shield]][release]
[![Downloads][downloads-shield]][release]
[![License][license-shield]](LICENSE)
[![Tests][tests-shield]][tests]
[![HACS Validation][hacs-validation-shield]][hacs-validation]

Read your BLUETTI power station **locally** in Home Assistant, over the Modbus TCP
interface built into the device. No account, no API key, no cloud service - your
readings keep arriving even when your internet connection or the BLUETTI cloud is
down.

Register maps and field decoding come from
[bluetti-community/bluetti-modbus](https://github.com/bluetti-community/bluetti-modbus)
(published on PyPI as `bluetti-modbus`), built from BLUETTI's own official register
documentation and verified against real hardware.

## Features ✨

* **Fully local.** Nothing leaves your network. Works alongside the cloud-based
  [BLUETTI](https://github.com/bluetti-official/bluetti-home-assistant) integration on
  the same device if you want both.
* **Set up from the UI.** No YAML - add the integration, enter the IP address, done.
* **Entities built from the device's own register map.** Every field the device
  reports becomes an entity, with the right device class, unit and precision applied
  automatically. Nothing is hard-coded per model.
* **Real controls, not just readings.** On Balco 260: AC output, grid charging and
  grid feed-in switches, plus the two battery SoC threshold settings.
* **Proper device structure.** The battery is its own sub-device; S Meter's three
  phases each get their own, linked back to the meter.
* **Stable entity IDs.** Entities are keyed on the device's real serial number read
  over Modbus, so they survive an IP change, a backup restore, or a move to a new
  Home Assistant instance.
* **Diagnostics built in.** One-click download for bug reports, with the address and
  serial numbers redacted.
* **Conservative polling.** One shared connection, one request at a time, 30 second
  interval - this device's Modbus stack is fragile under load, and this integration
  is deliberately gentle with it.

## Supported devices 🔋

| Device | Status | Notes |
| --- | --- | --- |
| **Balco 260** | ✅ Confirmed | Full support: 119 fields, switches, SoC thresholds, battery sub-device. Verified against real hardware and BLUETTI's official register spec. |
| **S Meter** | ✅ Confirmed | 31 fields, per-phase sub-devices. Verified against real hardware. |
| **AC500** | ✅ Confirmed | 30 fields, switches, SoC thresholds. Verified against real hardware by the community, not yet BLUETTI-support-confirmed like Balco 260/S Meter. |

**EP2000 is not supported.** Its Modbus TCP support was withdrawn pending
confirmation the device exposes Modbus TCP at all - a real-world report found an
EP2000 with no reachable Modbus TCP port and no local web UI
([bluetti-official/bluetti-home-assistant#125](https://github.com/bluetti-official/bluetti-home-assistant/issues/125)).

Have a different BLUETTI model? Register data is welcome - see
[bluetti-community/bluetti-registers](https://github.com/bluetti-community/bluetti-registers).

## Prerequisites 🔌

Modbus TCP is **turned off by default** on the device. You need to enable it through
the device's own local web server first.

1. Make sure your computer is on the same network as the device.
2. Find the device's IP address on the network configuration page of the BLUETTI app.
3. Open that IP address in a browser to reach the device's local web page.
4. Sign in. The username is `admin`; the password is your BLUETTI app password, or
   blank if you never set one.
5. Go to **Settings** → **Modbus TCP**, turn on **Enable**, set **Port** to `502`,
   and select **Settings** to save.

Give the device a fixed address in your router - if its address changes, Home
Assistant will stop reaching it.

> [!NOTE]
> Modbus TCP is only available on some models and firmware versions. If you cannot
> find these settings, your device does not support it yet.

## Installation ⚙️

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bluetti-community&repository=hassio-bluetti-modbus&category=integration)

_or manually:_

1. [Install HACS](https://hacs.xyz/docs/setup/download) if you don't have it yet.
2. In HACS, open the **⋮** menu → **Custom repositories**.
3. Add `https://github.com/bluetti-community/hassio-bluetti-modbus` with category
   **Integration**.
4. Find **Bluetti Modbus** in HACS and install it.
5. **Restart Home Assistant.**

### Manually

1. Copy `custom_components/bluetti_modbus` into your Home Assistant configuration's
   `custom_components/` directory.
2. Restart Home Assistant.

## Configuration 🛠️

1. Go to **Settings** → **Devices & services** → **+ Add integration**.
2. Search for **Bluetti Modbus**.
3. Fill in:
   * **Address** - the IP address or hostname of your device.
   * **Port** - `502` unless you changed it on the device.
   * **Type** - Balco 260, S Meter, or AC500.

The device is contacted straight away, so a wrong address or a device with Modbus TCP
still disabled fails immediately rather than after setup.

The poll interval is fixed at 30 seconds and is not configurable: this device's
Modbus TCP stack has been observed becoming unresponsive under heavier polling, to
the point of needing a factory reset to recover.

## Entities 🧩

Entities are generated from whatever the device's register map reports, so the exact
set depends on your model.

### Sensors

* **Battery** - voltage, current, SoC, SoH, temperature, cycle count, lifetime
  charged/discharged energy, time to full/empty. On its own **Battery** sub-device.
* **Solar** - per-string (MPPT 1-4) voltage, current and power, plus combined PV
  input power and lifetime energy.
* **Grid** - frequency, import/export power, per-phase voltage/current/power, and
  lifetime import/export energy counters.
* **AC output** - power, per-phase voltage/current/power, lifetime output energy.
* **Inverter** - status, type, per-inverter power/voltage/current, inverter totals.
* **Diagnostics** - serial numbers, firmware versions, cell/pack/sensor counts,
  protection and alarm registers.
* **S Meter** - per-phase voltage, current, active/reactive/apparent power and power
  factor on three **Phase A/B/C** sub-devices, with the totals and averages on the
  meter itself.

### Switches (Balco 260)

* **AC Output** - turn the AC output on or off.
* **Grid Charging** - allow or block charging from the grid.
* **Grid Feed-in** - allow or block exporting to the grid.

### Numbers (Balco 260)

* **Min Discharge Limit (SoC Low)** - 5-90%.
* **Max Charge Limit (SoC High)** - 0-100%.

### Binary sensors (S Meter)

* **Online** - whether the meter is reporting.

## Known limitations ⚠️

These are device or firmware limitations found on real hardware, not bugs in the
integration - documented here so you don't have to rediscover them.

* **Per-inverter "(Single)" fields read 0.** `ac_o_p_local`, `g_i_p_local`,
  `g_i_e_local`, `g_o_e_local` and `ac_o_e_local` return a clean, error-free 0 on a
  real Balco 260 while their `_total` counterparts change normally at the same
  moment. They are **disabled by default**; the `_total`/phase-1 sensors are the
  ones to use. Reported to BLUETTI.
* **Inverter fault/warning are not exposed.** The library's fault and warning enums
  only decode their "no fault"/"no warning" value, so those sensors would go blank
  exactly when something went wrong. They will return once real codes can be
  decoded.
* **Battery packs beyond the first are not shown.** On a Balco 260 with several
  BC260 packs, every pack past the first reads 0 for every field over its own Modbus
  slave address - indistinguishable from no pack at all. The aggregate totals are
  correct and are shown. Tracked in
  [bluetti-modbus#55](https://github.com/bluetti-community/bluetti-modbus/issues/55) -
  **data from multi-pack owners is wanted there.**
* **Write confirmations come back with a corrupt address.** Writing a switch or a
  SoC threshold applies correctly on the device, but the device's Modbus
  confirmation echoes a wrong register address. The integration recognises this
  specific firmware bug and treats the write as successful, logging a warning each
  time. Reported to BLUETTI.
* **One connection at a time.** The device accepts very few simultaneous Modbus TCP
  connections. If something else on your network already polls it, Home Assistant
  may not get through.

## Troubleshooting 🐛

### Enable debug logging

Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: info
  logs:
    custom_components.bluetti_modbus: debug
```

Logs are under **Settings** → **System** → **Logs**.

### Download diagnostics

1. **Settings** → **Devices & services** → **Bluetti Modbus**.
2. Open the device, then the **⋮** menu → **Download diagnostics**.

The file contains every field the device last reported, with the address and serial
numbers redacted. Attach it to a bug report - almost every question about a missing
or wrong sensor is answered by one.

### Common problems

| Symptom | Likely cause |
| --- | --- |
| Setup fails with "cannot connect" | Modbus TCP not enabled on the device, wrong port, or the device is unreachable. Re-check the [prerequisites](#prerequisites-). |
| All entities go unavailable | The device stopped answering. Check it is powered on and reachable; entities recover on the next successful poll. |
| A sensor is stuck at 0 | Check [Known limitations](#known-limitations-) first - several fields are genuinely never populated by the device. |
| A sensor is missing entirely | The device simply doesn't report that field. Entities are built from what the register map returns - a diagnostics download will show exactly what came back. |

## Contributing 🤝

Bug reports, register data and real-hardware confirmations are all welcome. For
anything about a missing or wrong value, please attach a diagnostics download.

The test suite (100% line coverage enforced) runs in CI on every pull request. To run
it locally with nothing but Docker installed:

```bash
./test.sh
```

This builds `Dockerfile.test` and runs the same `coverage run` /
`coverage report --fail-under=100` steps CI does.

This integration bundles its own copy of `bluetti-modbus`
(`custom_components/bluetti_modbus/vendor/`) rather than depending on it via PyPI.
Run `scripts/vendor_bluetti_modbus_lib.sh` to pick up a newer version.

## Related projects 📦

* [bluetti-community/bluetti-modbus](https://github.com/bluetti-community/bluetti-modbus) -
  the Modbus library this integration is built on.
* [bluetti-community/bluetti-registers](https://github.com/bluetti-community/bluetti-registers) -
  the register maps themselves.
* [bluetti-official/bluetti-home-assistant](https://github.com/bluetti-official/bluetti-home-assistant) -
  the cloud-based BLUETTI integration. Can be used at the same time as this one.
* [Patrick762/hassio-bluetti-modbus](https://github.com/Patrick762/hassio-bluetti-modbus) -
  this repository started as a fork of Patrick762's and has since diverged
  significantly (coordinator and entity handling, retry behaviour, multi-pack
  support, device coverage). Patrick762 still maintains his own version
  independently.
* [Patrick762/hassio-bluetti-bt](https://github.com/Patrick762/hassio-bluetti-bt) -
  Bluetooth integration for BLUETTI's portable power stations (AC/EB/EL/PR series).

## Disclaimer

This integration is not affiliated with, endorsed by, or supported by BLUETTI. It is
provided without any warranty; use it at your own risk.

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[release-shield]: https://img.shields.io/github/v/release/bluetti-community/hassio-bluetti-modbus.svg
[release]: https://github.com/bluetti-community/hassio-bluetti-modbus/releases
[downloads-shield]: https://img.shields.io/github/downloads/bluetti-community/hassio-bluetti-modbus/total.svg
[license-shield]: https://img.shields.io/github/license/bluetti-community/hassio-bluetti-modbus.svg
[tests-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml/badge.svg
[tests]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml
[hacs-validation-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml/badge.svg
[hacs-validation]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml
