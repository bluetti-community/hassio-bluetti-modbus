# Releasing

## Version numbers

Semantic versioning: `MAJOR.MINOR.PATCH`.

- **MAJOR** — a change that breaks an existing setup: an entity that disappears
  or is renamed, a config entry that has to be re-created, a minimum Home
  Assistant version that rises.
- **MINOR** — a new device type, new entities, a new option.
- **PATCH** — a fix, a vendored library bump that changes nothing visible.

The version in `custom_components/bluetti_modbus/manifest.json` is bumped in
the same commit as the change it ships, and the release tag is that exact
version with no `v` prefix. The one commit of its own is the final release of
a beta series (below).

## Prereleases

A prerelease is `MAJOR.MINOR.PATCH-beta.N`: newer than every earlier release,
older than `MAJOR.MINOR.PATCH`. It is published as a GitHub prerelease, which
HACS offers only to someone who enables beta versions for the repository.

**A change on `main` that needs a test on hardware before it ships** (a new
connection layer, a rising Home Assistant minimum):

1. The pull request bumps the manifest to `X.Y.Z-beta.1`. It is merged, and
   `X.Y.Z-beta.1` is tagged on that commit of `main`.
2. A fix during the test is another pull request on `main`, bumping to
   `X.Y.Z-beta.2`, tagged the same way.
3. Once the test passes, one commit on `main` changes the manifest to `X.Y.Z`
   and nothing else, and `X.Y.Z` is tagged on it.

Every beta of a version is then an ancestor of that version, and its release
comes after them in the list. Never tag `X.Y.Z` on a commit older than its
betas.

**A gated device** (`<MODEL>_CONFIRMED = False` on `main`): the test build is
cut from a `<device>-beta` branch with the flag enabled there only, and that
branch is never merged. Confirmation flips the flag on `main` in a normal
release. A stable release from `main` while such a beta is out is newer than
the beta for HACS, so the beta is re-cut on top of it as the next version's
`-beta.1`.

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
