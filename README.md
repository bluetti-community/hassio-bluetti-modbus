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
* **Set up from the UI.** No YAML. S Meter and Balco 260 are discovered automatically on
  your network (see [Configuration](#configuration-)) - for everything else, add the
  integration, enter the IP address, done.
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
| **Balco 260** | ✅ Confirmed | Full support: 107 fields, switches, SoC thresholds, battery sub-device, one sub-device per BC260 expansion pack. Verified against real hardware and BLUETTI's official register spec. |
| **S Meter** | ✅ Confirmed | 31 fields, per-phase sub-devices. Verified against real hardware. |
| **AC500** | ✅ Confirmed | 30 fields, switches, SoC thresholds. Verified against real hardware by the community, not yet BLUETTI-support-confirmed like Balco 260/S Meter. No mDNS: manual setup ([#98](https://github.com/bluetti-community/hassio-bluetti-modbus/issues/98)). Never address a Modbus unit id other than 1 on it - a read at any other unit id froze its Modbus TCP stack until a power cycle ([bluetti-registers#13](https://github.com/bluetti-community/bluetti-registers/issues/13)). |
| **AC200L / AC200L2** | ✅ Confirmed | 30 fields, AC/DC output switches, SoC thresholds (read-only). Contributed from and confirmed on a real AC200L2, cross-checked against its BLE readings ([bluetti-registers#31](https://github.com/bluetti-community/bluetti-registers/issues/31)); energy and PV fields not yet seen non-zero. Absent from BLUETTI's official register list; the device calls itself "AC200L" - whether an original AC200L exposes Modbus TCP at all is unknown. No mDNS: manual setup. |
| **EP500Pro** | ✅ Confirmed | 32 fields, AC/DC output switches (switched on real hardware), SoC thresholds and grid charging read-only. Modbus TCP appeared with IoT firmware 9041.17 (enable it on the unit's local web page, port 80); AC500's register set read on two real units and run in Home Assistant by one of them, every value matching the app ([bluetti-registers#35](https://github.com/bluetti-community/bluetti-registers/issues/35)); energies and per-string PV fields not yet seen non-zero. Absent from BLUETTI's official register list; the profile carries the device's own type string, `EP500P`. No mDNS: manual setup. |

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
4. Sign in. The username is `admin`; the password is your BLUETTI **app account**
   password (not a device-local one), or blank if you never set one.
5. Go to **Settings** → **Modbus TCP**, turn on **Enable**, set **Port** to `502`,
   and select **Settings** to save.

Give the device a fixed address in your router - if its address changes, Home
Assistant will stop reaching it.

> [!NOTE]
> Modbus TCP is only available on some models and firmware versions. If you cannot
> find these settings, your device does not support it yet. The page is the same
> "Bluetti Manager" on a Balco 260 and on an AC200L2.

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

### Discovered automatically (S Meter, Balco 260)

Both devices advertise themselves on the local network (mDNS/zeroconf) once Modbus TCP
is enabled (see [Prerequisites](#prerequisites-)) - Home Assistant finds them on its own,
usually within a minute or two:

1. Go to **Settings** → **Devices & services**. A **Discovered** card shows your device.
2. Select **Configure**, confirm, done.

If it doesn't show up (a different subnet/VLAN than Home Assistant, for example, or
mDNS/multicast blocked on your network), use manual setup below instead - both reach the
same integration either way.

BLUETTI has told us a future Balco 260 firmware will advertise the same way the S Meter
does (a `_bluetti._tcp` service named after the model and serial number, instead of
today's generic `_http._tcp` "Bluetti HEMS"). Both forms are recognised, so discovery
keeps working across that update without any change on your side.

Adding a model that isn't discovered yet? The library's hardware-testing guide explains how
to find out what your device announces (an mDNS browse) and what its own web page knows
(its WebSocket, through your browser's developer tools) - see
[HARDWARE_TESTING.md, "What the device's own web page knows"](https://github.com/bluetti-community/bluetti-modbus/blob/main/HARDWARE_TESTING.md#5-what-the-devices-own-web-page-knows-mdns-name-modbus-tcp-status-firmware).

### Manual setup (everything else, or if discovery doesn't find your device)

1. Go to **Settings** → **Devices & services** → **+ Add integration**.
2. Search for **Bluetti Modbus**.
3. Fill in:
   * **Address** - the IP address or hostname of your device.
   * **Port** - `502` unless you changed it on the device.
   * **Type** - Balco 260, S Meter, AC500, AC200L / AC200L2, or EP500Pro (the AC500, the
     AC200L2 and the EP500Pro do not announce themselves on the network, so this is the
     only way to add them).

The device is contacted straight away, so a wrong address or a device with Modbus TCP
still disabled fails immediately rather than after setup.

The poll interval is fixed at 30 seconds and is not configurable: this device's
Modbus TCP stack has been observed becoming unresponsive under heavier polling, to
the point of needing a factory reset to recover.

## Entities 🧩

Entities are generated from whatever the device's register map reports, so the exact
set depends on your model.

### Sensors

* **Battery** - voltage, current, SoC, SoH, cycle count, lifetime charged/discharged
  energy. On its own **Battery** sub-device; each BC260 expansion pack on its own
  **Pack N** sub-device with the same sensors.
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

* **Twelve registers of the official list are not supported on a Balco 260** and no
  longer have a sensor: `b_t_avg` (average battery temperature), `b_time_to_full`/
  `b_time_to_empty` (the pack-level estimates - the `_total` ones, system-wide, work),
  `d_self_consumption`, and the per-inverter "(Single)" block except `pv_i_p_local`
  (`ac_o_p_local`, `g_i_p_local`, `pv_ac_p_local`, `g_i_e_local`, `g_o_e_local`,
  `ac_o_e_local`, `pv_i_e_local`, `pv_ac_e_local`). They read a flat 0 on a real unit
  over 11 days while their `_total`/phase-1 counterparts moved, and BLUETTI confirmed
  they are not supported on this device - the summary fields are the ones to use.
  Existing sensors for them are removed on upgrade. (Other models keep them, disabled
  by default; `pv_i_e_local` stays enabled on an AC500, where it is the only cumulative
  PV energy reading.)
* **`pv_i_p_local` repeats the PV total.** Unlike the fields above it carries
  real values, but it measures this one inverter - which on a single-inverter
  system is the whole system, so it repeats `pv_i_p_total` and, with only one PV
  string in use, `pv_1_i_p`. Also **disabled by default**; enable it if you run
  several inverters together. (`pv_i_e_local` stays enabled: on an AC500 it is
  the only cumulative PV energy reading there is.)
* **Inverter fault/warning are not exposed.** The library's fault and warning enums
  only decode their "no fault"/"no warning" value, so those sensors would go blank
  exactly when something went wrong. They will return once real codes can be
  decoded.
* **BC260 expansion packs each get their own sub-device** ("Pack 2", "Pack 3", ...),
  with the same sensors as the built-in battery: type, serial number, voltage, current,
  SoC, SoH, cycle count, firmware, energies. Confirmed on a Balco 260 with three packs.
  A pack slot that answers only its serial number - a firmware issue BLUETTI has
  confirmed and plans to fix - shows its sensors as **unavailable** rather than as
  0 % / 0 V; that is the device saying nothing, not a fault. The aggregate totals are
  shown on the main device as before.
* **Write confirmations name the device's internal register, not the Modbus one.**
  Writing a switch or a SoC threshold applies correctly on the device, but the Modbus
  confirmation echoes the same setting's address in the device's own internal register
  space (the one the BLUETTI app uses - 2022 for the min-discharge threshold written
  at 57016, 2207 for grid charging written at 57009, and so on; confirmed on real
  hardware for all five writable registers) instead of the Modbus address. The
  bundled [bluetti-modbus](https://github.com/bluetti-community/bluetti-modbus)
  library recognises this and treats the write as successful - silently when the
  echoed address is the one on file for that register, with a warning naming it
  otherwise. Reported to BLUETTI.
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

The file contains every field the device last reported, plus the raw register words
behind them (read once more at download time), with the address and serial numbers
redacted. Attach it to a bug report - almost every question about a missing or wrong
sensor is answered by one, and the raw words settle whether a wrong value is a decode
problem on our side or what the device actually sent.

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

The read-only register probe (registers a Balco 260 is *not* documented to have, and
which Modbus slave ids answer with which pack) lives in the library, next to its
hardware-testing guide:
[bluetti-modbus/script/probe_unexplored_registers.py](https://github.com/bluetti-community/bluetti-modbus/blob/main/script/probe_unexplored_registers.py).
Stop Home Assistant's polling first (disable the integration entry) before running it
against a live unit.

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
