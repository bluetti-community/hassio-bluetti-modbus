# BLUETTI Modbus for Home Assistant

- Connect your BLUETTI power station or S Meter to Home Assistant over the Modbus TCP interface built into the device.
- Fully local: no account, no API key, no cloud service. Readings keep arriving when your internet connection or the BLUETTI cloud is down.
- Readings, switches and SoC limits for 12 models, set up from the UI.

[![Release][release-shield]][release]
[![Downloads][downloads-shield]][release]
[![License][license-shield]](LICENSE)
[![Tests][tests-shield]][tests]
[![Hassfest][hassfest-shield]][hassfest]
[![Repository validation][validation-shield]][validation]

> [!IMPORTANT]
> **Home Assistant 2026.11 includes a BLUETTI Modbus integration for the Balco 260.** It gives you the Balco 260's readings with nothing to install. This repository covers more models and adds controls. See [Also available in Home Assistant](#also-available-in-home-assistant) for how the two relate.

## Contents

- [Features](#features)
- [Supported devices](#supported-devices)
- [Also available in Home Assistant](#also-available-in-home-assistant)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Setup](#setup)
- [Data updates](#data-updates)
- [Entities](#entities)
- [Actions](#actions)
- [Energy dashboard](#energy-dashboard)
- [Automation example](#automation-example)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Related projects](#related-projects)
- [Disclaimer and license](#disclaimer-and-license)

## Features

- **Local.** Nothing leaves your network. It can run alongside the [cloud-based BLUETTI integration](https://github.com/bluetti-official/bluetti-home-assistant) on the same device.
- **Set up from the UI.** The Balco 260, Balco 500 and S Meter are discovered on your network. Other models take an IP address and a device type.
- **Entities from the register map.** Every field the device reports becomes an entity with the right device class, unit and precision.
- **Controls.** Output, grid charging and feed-in switches, SoC limits, and the AC charging mode, on the models where the write is confirmed on a real unit.
- **Device structure.** The built-in battery and each PV input are sub-devices of the station. Expansion packs and an EP2000's battery are linked devices. The S Meter's three phases are sub-devices of the meter.
- **Stable entities.** Entities are keyed on the serial number read from the device, so they survive an IP change or a move to a new Home Assistant instance.
- **Diagnostics.** One-click download for bug reports, with the address and serial numbers redacted.
- **Translated.** English, French, German, Dutch, Lithuanian, Portuguese (Portugal and Brazil) and Ukrainian.

## Supported devices

| Device | Setup | Controls | Evidence |
| --- | --- | --- | --- |
| **Balco 260** | Discovered | AC output, grid charging, grid feed-in, SoC low/high limits | Real hardware + BLUETTI spec |
| **Balco 500** | Discovered | Grid feed-in, SoC low/high limits | [Real unit](https://github.com/bluetti-community/bluetti-registers/issues/68) |
| **S Meter** | Discovered | Read-only | Real hardware + BLUETTI spec |
| **FridgePower** | IP address | DC output, grid charging | [3 units](https://github.com/bluetti-community/bluetti-registers/issues/38) |
| **AC500** | IP address | AC output, DC output | [Real unit](https://github.com/bluetti-community/bluetti-registers/issues/13) |
| **EP500Pro** | IP address | AC output, DC output, grid charging | [2 units](https://github.com/bluetti-community/bluetti-registers/issues/35) |
| **AC200L** | IP address | AC output, DC output, AC power lifting, AC charging mode | [2 units](https://github.com/bluetti-community/bluetti-registers/issues/31) |
| **AC240**, **AC240P** | IP address | AC output, DC output, grid charging, AC ECO, AC power lifting | [Real unit](https://github.com/bluetti-community/hassio-bluetti-modbus/issues/176) |
| **Apex 300** | IP address | AC output, DC output, grid charging, AC charging mode | [3 units](https://github.com/bluetti-community/bluetti-registers/issues/49) |
| **EP2000** | IP address | AC output, grid charging, grid feed-in, SoC low/high limits | [4 units](https://github.com/bluetti-community/hassio-bluetti-modbus/issues/145) |
| **Balco Transfer Hub** | IP address | Read-only | [2 hubs](https://github.com/bluetti-community/bluetti-registers/issues/29) |

Every field a device reports is shown as a reading. The controls listed are the writes confirmed on a real unit.

**Not possible:** the EP600 has no local web page, so no Modbus TCP.

Have another BLUETTI model? Register data is welcome in [bluetti-registers](https://github.com/bluetti-community/bluetti-registers).

<details>
<summary><b>Per-device notes</b></summary>

**Balco 260**

- With an energy meter paired in the BLUETTI app (a Shelly Pro 3EM, for example), the grid entities report the meter's readings: the household's grid connection, not the Balco's own port. A three-phase meter on a single-phase installation reports three phases, with the same voltage on each and no current on phases 2-3. Those entities can be disabled.
- A pack slot that answers only its serial number shows its sensors as **unavailable** rather than 0 % or 0 V. This is a firmware issue confirmed by BLUETTI.

**FridgePower**

- The SoC limits refuse writes and stay read-only. The AC output switch is left untried: it powers the fridge.
- There is no grid feed-in switch: the unit is off-grid only.
- One PV input, one inverter and one phase.

**AC500, EP500Pro, AC200L, Apex 300** share one register layout. An AC200PL reads with the AC200L type.

- The SoC limits are read-only.
- There is no per-pack data: the pack registers show the pack selected in the app, and that selector is not reachable over Modbus TCP.
- On the AC500 and EP500Pro, never address a Modbus unit id other than 1: it freezes their Modbus TCP until a power cycle.
- On the Apex 300, Grid Charging is the Custom working mode's "Charge From Grid" setting. It has no effect in Backup mode.
- On the Apex 300, the AC charging mode can be changed, from Home Assistant as from the BLUETTI app, only while the unit's physical charging mode selector is on Auto.
- Energy and per-string PV fields have not been seen non-zero on the EP500Pro and AC200L.

**AC240, AC240P.** Add an AC240P with the AC240 type.

- The built-in battery reads unknown except while the BLUETTI app shows the battery page.
- On an AC240P, the DC Output switch also switches the USB ports.

**EP2000**

- Its two MPPTs are sub-devices named **MPPT 1** and **MPPT 2**.
- The battery (an HV800 controller over stacked B700 packs) is a device of its own.
- Modbus TCP is opened by the BLUETTI app's **Virtual Power Plant - Join VPP** row (choose a provider, port 502), not on the web page. Providers differ by region, and updating the app can bring a missing row. A virtual power plant can let an aggregator charge and discharge the battery, so check what your provider's option authorises first.
- Grid Charging only has an effect in the app's Custom working mode, while its time-of-use settings allow charging. ([evidence](https://github.com/bluetti-community/bluetti-registers/issues/42#issuecomment-6709361887))
- The grid entities measure the EP2000's own grid port, not the house's connection. With AC-coupled solar, do not use Total Grid Power as the grid meter in the Energy dashboard. ([evidence](https://github.com/bluetti-community/hassio-bluetti-modbus/issues/145#issuecomment-5987109089))

**Balco Transfer Hub** is a grid-tie controller, not a power station.

- It has no battery: the SoC, battery voltage and PV entities show the connected station's values.
- Working mode, feed-in limit and schedule stay in the app: this firmware has no writable register.

</details>

## Also available in Home Assistant

Home Assistant 2026.11 ships a [BLUETTI Modbus integration](https://www.home-assistant.io/integrations/bluetti_modbus) for the Balco 260. If its readings cover your needs, use it: there is nothing to install.

> [!NOTE]
> Both use the domain `bluetti_modbus`, so installing this repository **replaces** the built-in integration. You run one or the other, never both.

| | Built-in | This repository |
| --- | --- | --- |
| Models | Balco 260 | All [supported devices](#supported-devices) |
| Readings | Yes | Yes, plus firmware slots, alarms and network status |
| Switches and SoC limits | No | Yes |
| Network discovery | No | Yes |
| Battery, PV and pack sub-devices | No | Yes |
| Rides out a failed poll on the last values | No | Yes, see [Data updates](#data-updates) |
| Support | Home Assistant project | [This repository's issues](https://github.com/bluetti-community/hassio-bluetti-modbus/issues) |

New features land here first and are then proposed to Home Assistant, so the built-in integration follows behind.

### Moving from the built-in integration to this repository

Install this repository and restart Home Assistant. Your setup is taken over: device, entity IDs and history are kept, and the new entities and sub-devices appear. Confirmed on a Balco 260.

A setup that uses a Modbus unit id other than 1 is not taken over: it logs an error, and the device has to be removed and added again.

### Going back to the built-in integration

1. Open this repository's page in **Settings → Marketplace**.
2. Select **⋮ → Uninstall → Delete and uninstall**. This removes every device set up with this integration, including those the built-in integration does not support.
3. Restart Home Assistant.
4. Add **BLUETTI Modbus** again from **Settings → Devices & services**.

## Prerequisites

Modbus TCP is **turned off by default**. Turn it on from the device's own web page:

1. Make sure your computer is on the same network as the device.
2. Find the device's IP address on the network configuration page of the BLUETTI app.
3. Open that address in a browser.
4. Sign in as `admin`. The password is the **device's Bluetooth password** from the BLUETTI app, or blank if you never set one. It is not your app account password.
5. Go to **Settings → Modbus TCP**, turn on **Enable**, set **Port** to `502`, and select **Settings** to save.
6. Close the page.

Give the device a fixed address in your router.

> [!NOTE]
> Modbus TCP is only available on some models and firmware versions. If you cannot find these settings, your device does not support it yet. On an Apex 300, IoT 8026.17 serves the page on your home network; on 8026.14 it may be reachable only through the unit's own Wi-Fi access point. An EP2000 has no switch on its page: see its [notes](#supported-devices).

## Installation

Requires **Home Assistant 2026.10.1 or newer**.

### Marketplace

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bluetti-community&repository=hassio-bluetti-modbus)

This repository is not in the Marketplace catalog, because it shares its domain with the built-in integration. Add it from its link:

1. Go to **Settings → Marketplace** and select **Add from link** in the upper-right corner. Home Assistant asks you to connect GitHub if you have not done so yet.
2. Enter `bluetti-community/hassio-bluetti-modbus` and select **Add**.
3. Open **BLUETTI Modbus** in the list and select **Install**.
4. Tick the box confirming that it replaces the built-in integration, then select **Install**.
5. Restart Home Assistant.

Installations made with HACS carry over when you update to Home Assistant 2026.11, with nothing to do. On Home Assistant 2026.10, add this repository to HACS as a custom repository of type **Integration**.

### Pre-release versions

Devices and features under test ship in a pre-release. The [releases page](https://github.com/bluetti-community/hassio-bluetti-modbus/releases) lists what each one carries.

- **Once:** on this repository's page in the Marketplace, select **⋮ → Install another version**, pick the version, and restart.
- **Every new one:** go to **Settings → Devices & services → Entities**, filter on the **BLUETTI Modbus** device of the Marketplace, enable the **Pre-release** entity, and turn it on.

To return to an earlier version, restore a backup.

### Manually

Copy `custom_components/bluetti_modbus` into your configuration's `custom_components/` directory and restart Home Assistant.

## Setup

### Discovered devices

The Balco 260, Balco 500 and S Meter announce themselves once Modbus TCP is on. Go to **Settings → Devices & services**, select **Configure** on the **Discovered** card, and confirm.

If nothing shows up, for example because of a separate VLAN or blocked multicast, add the device by its address.

### By IP address

[![Open your Home Assistant instance and start setting up BLUETTI Modbus.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bluetti_modbus)

Go to **Settings → Devices & services → Add integration**, search for **BLUETTI Modbus**, and fill in:

- **IP address** of the device.
- **Port:** `502`, unless you changed it on the device.
- **Device type:** your model.

The device is contacted straight away, so a wrong address or a device with Modbus TCP still off fails immediately.

### Changing a device's address

Select **⋮ → Reconfigure** on the entry. The device is checked at the new address, and the entry only moves there when the same unit answers.

## Data updates

The polling intervals are fixed, because this device's Modbus TCP stack has been seen becoming unresponsive under heavier polling, to the point of needing a factory reset.

- **Readings:** every 15 seconds.
- **Settings** (switches and SoC limits): every 60 seconds.
- **Network status** (Balco 260): read from the device's web page every 5 minutes.
- **Failed polls:** up to five in a row are ridden out on the last values before entities go unavailable. They recover on the next successful poll.

Home Assistant keeps one shared connection open and sends one request at a time. The device accepts very few simultaneous connections, and an EP2000 takes just one, so another Modbus client can lock this integration out, or be refused. To run one, disable the entry and restart Home Assistant first.

## Entities

The exact set depends on your model.

- **Battery:** voltage, current, SoC, SoH, cycle count, lifetime charged and discharged energy.
- **Solar:** voltage, current, power and input type per input, plus combined power and lifetime energy.
- **Grid:** frequency, import and export power, voltage, current and power per phase, lifetime import and export energy.
- **AC output:** power, voltage, current and power per phase, lifetime energy.
- **Inverter:** status, type, power, voltage and current per inverter, and totals.
- **Diagnostics:** serial numbers, firmware versions, counts, protection and alarm registers. Inverter faults and warnings show the number of active codes, with each code and its meaning as attributes. On a Balco 260, also the Wi-Fi signal.
- **S Meter:** voltage, current, active, reactive and apparent power and power factor per phase, plus totals and averages.
- **Switches and numbers:** AC Output, DC Output, Grid Charging, Grid Feed-in, AC ECO, AC Power Lifting, Min Discharge Limit (5-90 %) and Max Charge Limit (0-100 %), on the models listed in [Supported devices](#supported-devices).
- **Binary sensors:** Online (S Meter); BLUETTI cloud connection and Internet reachable (Balco 260).

> [!CAUTION]
> Don't switch the AC output off and on again within a few seconds, by hand or from an automation. On a Balco 260, off and on 13 seconds apart under load was followed by an inverter fault that switched the output off. No safe minimum interval is known.

## Actions

### Read registers

`bluetti_modbus.read_register`, from 3.5.0, reads raw holding registers while the integration keeps running, for tests and diagnostics. It returns the words as the device sent them:

```yaml
action: bluetti_modbus.read_register
data:
  config_entry_id: <your entry>
  address: 57016
  count: 2
# response: {address: 57016, values: [15, 95]}
```

Only addresses the device's profile already reads are accepted, at most one block long: 20 registers on a Balco 260 or FridgePower, 10 on a Transfer Hub, 50 otherwise. It is not available on the S Meter.

## Energy dashboard

| Dashboard entry | Entity |
| --- | --- |
| Solar production | Total PV Input Energy |
| Battery, energy in | Total Battery Charged Energy |
| Battery, energy out | Total Battery Discharged Energy |
| Battery, state of charge | Total Battery SoC |
| Grid consumption | Total Grid Import Energy |
| Grid return | Total Grid Export Energy |

The names can differ slightly by model. On an EP2000, read its [notes](#supported-devices) before using the grid entities.

## Automation example

Stop charging from the grid once the battery reaches 80 %. Replace the entity IDs with your own.

```yaml
alias: "Balco: stop grid charging at 80 %"
triggers:
  - trigger: numeric_state
    entity_id: sensor.balco_260_total_battery_soc
    above: 80
actions:
  - action: switch.turn_off
    target:
      entity_id: switch.balco_260_grid_charging_switch
mode: single
```

## Known limitations

These come from the devices and their firmware.

- **Twelve registers of BLUETTI's list are unsupported on a Balco 260** and have no sensor: BLUETTI confirmed it, and the `_total` fields are the ones to use.
- **Writes are confirmed under another address.** The device echoes its internal register rather than the Modbus one. The write applies, and the bundled library recognises this.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Setup fails to connect | Modbus TCP is off, the port is wrong, or the device is unreachable. See [Prerequisites](#prerequisites). |
| Setup says Modbus TCP is off or encrypted | The message gives the setting to change on the device's web page. Close that page before trying again. |
| All entities go unavailable | The device stopped answering. Check that it is on and reachable. Entities recover on the next successful poll. |
| A sensor is missing or stuck at 0 | The device does not report that field. A diagnostics download shows what came back. |

### Debug logs

Go to **Settings → Devices & services → BLUETTI Modbus**, select **⋮ → Enable debug logging**, reproduce the problem, then select **⋮ → Disable debug logging** to download the log.

### Diagnostics

Open the device, then select **⋮ → Download diagnostics**. The file holds every field the device last reported and the raw register words behind them, with the address and serial numbers redacted. Attach it to a bug report: it answers almost every question about a missing or wrong value.

## Contributing

Bug reports, register data and real-hardware confirmations are welcome.

The test suite enforces 100 % line coverage and runs on every pull request. To run it locally with only Docker installed:

```bash
./test.sh
```

The integration bundles its own copy of the library in `custom_components/bluetti_modbus/vendor/`. Run `scripts/vendor_bluetti_modbus_lib.sh` to update it.

To test a new model, see the library's [hardware testing guide](https://github.com/bluetti-community/bluetti-modbus/blob/main/HARDWARE_TESTING.md).

## Related projects

- [bluetti-modbus](https://github.com/bluetti-community/bluetti-modbus): the library this integration is built on, also used by the built-in integration.
- [bluetti-registers](https://github.com/bluetti-community/bluetti-registers): the register maps.
- [bluetti-official/bluetti-home-assistant](https://github.com/bluetti-official/bluetti-home-assistant): BLUETTI's cloud integration, usable at the same time.
- [Patrick762/hassio-bluetti-modbus](https://github.com/Patrick762/hassio-bluetti-modbus): the project this repository was forked from, maintained independently.
- [Patrick762/hassio-bluetti-bt](https://github.com/Patrick762/hassio-bluetti-bt): Bluetooth integration for BLUETTI's portable power stations.

## Disclaimer and license

This integration is not affiliated with, endorsed by, or supported by BLUETTI. It is provided without any warranty; use it at your own risk.

Released under the [MIT License](LICENSE).

[release-shield]: https://img.shields.io/github/v/release/bluetti-community/hassio-bluetti-modbus.svg
[release]: https://github.com/bluetti-community/hassio-bluetti-modbus/releases
[downloads-shield]: https://img.shields.io/github/downloads/bluetti-community/hassio-bluetti-modbus/total.svg
[license-shield]: https://img.shields.io/github/license/bluetti-community/hassio-bluetti-modbus.svg
[tests-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml/badge.svg
[tests]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/test.yml
[hassfest-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/hassfest_validation.yml/badge.svg
[hassfest]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/hassfest_validation.yml
[validation-shield]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml/badge.svg
[validation]: https://github.com/bluetti-community/hassio-bluetti-modbus/actions/workflows/HACS.yml
