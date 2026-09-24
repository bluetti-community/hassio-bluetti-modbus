# Releasing

## Version numbers

Semantic versioning: `MAJOR.MINOR.PATCH`.

- **MAJOR** — a change that breaks an existing setup: an entity that disappears
  or is renamed, a config entry that has to be re-created, a minimum Home
  Assistant version that rises.
- **MINOR** — a new device type, new entities, a new option.
- **PATCH** — a fix, a vendored library bump that changes nothing visible.

A gated device's test build is a prerelease, `MAJOR.MINOR.PATCH-beta.N`, cut
from a `<device>-beta` branch with the device's flag enabled there only.

The version in `custom_components/bluetti_modbus/manifest.json` is bumped in
the same commit as the change it ships, never in a commit of its own, and the
release tag is that exact version with no `v` prefix.

## Release notes

Written by hand, from the merged pull requests. GitHub's "Generate release
notes" button gives the skeleton (`.github/release.yml` sets the categories);
the text that ships says what changed for the person running it.

```markdown
## ✨ New Features
- **Short subject**: what it does, and what it was confirmed against. (#123)

## 🐛 Bug Fixes
- **Short subject**: the symptom, then the cause in one clause. (#124)

## 📦 Vendored library
- Everything the `bluetti-modbus` tag jump carries, inert items included.

**Full Changelog**: https://github.com/bluetti-community/hassio-bluetti-modbus/compare/<previous>...<this>
```

Rules that matter more than the layout:

- One line per change, leading with the subject in bold, ending with its pull
  request number.
- A device claim names the hardware it was confirmed on, or says it is untested.
- The vendored-library section lists **everything** the tag jump carries, not
  only what the integration uses.
- No release is shipped until its GitHub release exists: the tag alone does not
  reach HACS, and the zip asset is built by the release workflow.
