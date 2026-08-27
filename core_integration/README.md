# Core-track integration (not submitted)

This directory mirrors the file layout a real `home-assistant/core` PR would
have: `homeassistant/components/bluetti_modbus/` and
`tests/components/bluetti_modbus/`. It follows the pattern from
[Home Assistant's Modbus modernization announcement](https://developers.home-assistant.io/blog/2026/07/05/modernizing-modbus/) -
`async_get_unit`/`async_get_temporary_unit` for a connection shared through
HA's own `modbus` integration, matching
[`sofar`](https://github.com/home-assistant/core/tree/dev/homeassistant/components/sofar),
the reference integration named in that announcement.

This code is **not part of the HACS integration** shipped from this repo's
`custom_components/` - it's kept separate, on this branch, for review and
soak time before ever being proposed to `home-assistant/core`. See the
repo-level plan for the full staged rollout and what's still blocking an
actual submission (PyPI publishing, a `home-assistant/brands` entry,
`home-assistant.io` docs - see `quality_scale.yaml`'s `todo` items).

## How this was actually verified

`homeassistant.components.modbus`'s `async_get_unit`/`async_get_temporary_unit`
aren't in any PyPI release yet (this feature landed after the last release
this was written against) - so verifying this code needs a real
`home-assistant/core` checkout, not just a `pip install homeassistant`.
`home-assistant/core`'s `dev` branch also now requires Python 3.14.

```bash
# From a Python 3.14 interpreter:
git clone --depth 1 --filter=blob:none --branch dev https://github.com/home-assistant/core.git ha-core
python3.14 -m venv ha-venv
ha-venv/bin/pip install -e ha-core --no-deps
ha-venv/bin/pip install -r ha-core/requirements.txt -r ha-core/requirements_test.txt
ha-venv/bin/pip install "modbus-connection[pymodbus,tmodbus]" paho-mqtt aiohasupervisor ruff

# Drop this integration's code into the checkout:
cp -r homeassistant/components/bluetti_modbus ha-core/homeassistant/components/
cp -r tests/components/bluetti_modbus ha-core/tests/components/

# Also needs bluetti-modbus-lib installed (the real requirement once
# published; for now, from the fork directly):
ha-venv/bin/pip install "bluetti-modbus-lib@git+https://github.com/bluetti-community/bluetti-modbus-lib.git@main"

cd ha-core
../ha-venv/bin/python3.14 -m pytest tests/components/bluetti_modbus/ -v
PATH="../ha-venv/bin:$PATH" ../ha-venv/bin/python3.14 -m script.hassfest \
    --integration-path homeassistant/components/bluetti_modbus
```

Verified this way: all tests pass, and `hassfest` reports every check clean
except the one it's supposed to (`New integrations are required to at least
reach the Bronze tier`) - the real, expected blocker until the `todo` items
in `quality_scale.yaml` are resolved.
