#!/usr/bin/env node
// One version, declared in six manifests because each provider reads a different
// one. Drift is silent until someone asks which version they are running.
//
// Usage: node scripts/validate-versions.mjs [--ahead-of-latest-tag]

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'

const ROOT = process.cwd()
const SEMVER_RE = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)*$/

const errors = []
const err = (m) => errors.push(m)

const dirs = (p) =>
  existsSync(p)
    ? readdirSync(p, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name)
    : []

const readJson = (rel) => {
  const abs = join(ROOT, rel)
  if (!existsSync(abs)) return null
  try {
    return JSON.parse(readFileSync(abs, 'utf8'))
  } catch (e) {
    err(`${rel}: invalid JSON — ${e.message}`)
    return undefined
  }
}

// Claude Code caches by version string, so a release reusing the previous one
// never reaches existing installs. Comparing against the latest tag rather than
// main means one bump per release cycle, not one per PR: once the version leads
// the tag, every later PR in that cycle passes untouched.
if (process.argv.includes('--ahead-of-latest-tag')) {
  const parse = (v) => v.replace(/^v/, '').split('.').map(Number)
  const cmp = (a, b) => {
    const [x, y] = [parse(a), parse(b)]
    for (let i = 0; i < 3; i++) {
      const d = (x[i] || 0) - (y[i] || 0)
      if (d) return d
    }
    return 0
  }

  let latest = ''
  try {
    latest = execFileSync('git', ['tag', '-l', 'v[0-9]*', '--sort=-v:refname'], { encoding: 'utf8' })
      .split('\n')[0].trim()
  } catch (e) {
    console.log(`  ERROR  could not list tags — ${e.message}`)
    process.exit(1)
  }
  if (!latest) {
    console.log('no release tag yet, so there is nothing to be ahead of.')
    process.exit(0)
  }

  const manifest = dirs(join(ROOT, 'plugins'))
    .map((plugin) => readJson(`plugins/${plugin}/plugin.json`))
    .find((m) => m?.version)
  if (!manifest) {
    console.log('  ERROR  no plugin declares a version to compare against the tag')
    process.exit(1)
  }
  if (cmp(manifest.version, latest) <= 0) {
    console.log(`  ERROR  the manifests declare ${manifest.version}, but tag ${latest} is already released.`)
    console.log('         Bump the version in every plugin manifest before merging.')
    process.exit(1)
  }
  console.log(`version ${manifest.version} leads the latest release tag ${latest}.`)
  process.exit(0)
}

const sources = []
const declare = (label, rel, value, required) => sources.push({ label, rel, value, required })

for (const plugin of dirs(join(ROOT, 'plugins'))) {
  for (const [provider, rel] of [
    ['Agent Plugins', `plugins/${plugin}/plugin.json`],
    ['Claude', `plugins/${plugin}/.claude-plugin/plugin.json`],
    ['Codex', `plugins/${plugin}/.codex-plugin/plugin.json`],
  ]) {
    const manifest = readJson(rel)
    if (manifest === null) {
      err(`${rel} is missing`)
    } else if (manifest) {
      declare(`${plugin} (${provider})`, rel, manifest.version, true)
    }
  }
}

// Deliberately absent from both catalogs: Claude Code always prefers
// plugin.json's version, so a version here would be silently ignored and could
// only ever drift. The check stays in case one appears anyway.
for (const [label, rel] of [
  ['Claude catalog', '.claude-plugin/marketplace.json'],
  ['Codex catalog', '.agents/plugins/marketplace.json'],
]) {
  const catalog = readJson(rel)
  if (!catalog) continue
  for (const entry of catalog.plugins ?? []) {
    if (entry?.version !== undefined) {
      declare(`${label} entry "${entry?.name ?? 'unnamed'}"`, rel, entry.version, false)
    }
  }
}

for (const source of sources) {
  if (source.value === undefined || source.value === null || source.value === '') {
    if (source.required) err(`${source.rel}: "version" is missing — Codex requires it and the release tag is checked against it`)
    continue
  }
  if (typeof source.value !== 'string') {
    err(`${source.rel}: "version" must be a string, got ${JSON.stringify(source.value)}`)
  } else if (!SEMVER_RE.test(source.value)) {
    err(`${source.rel}: "version" is "${source.value}", which is not a semantic version (MAJOR.MINOR.PATCH)`)
  }
}

const found = sources.filter((s) => typeof s.value === 'string' && s.value !== '')
const distinct = [...new Set(found.map((s) => s.value))]

if (distinct.length > 1) {
  err(`${distinct.length} different versions declared across ${found.length} manifests: ${distinct.sort().join(', ')}`)
  // Grouped so the odd one out is visible without diffing six files by hand.
  for (const version of distinct.sort()) {
    console.log(`  ${version}`)
    for (const source of found.filter((s) => s.value === version)) {
      console.log(`    ${source.label.padEnd(28)} ${source.rel}`)
    }
  }
  console.log('')
}

for (const e of errors) console.log(`  ERROR  ${e}`)
if (errors.length) {
  console.log(`\n${errors.length} error(s). Not ready to publish.`)
  process.exit(1)
}
console.log(`version ${distinct[0]} agreed across ${found.length} manifest(s).`)
