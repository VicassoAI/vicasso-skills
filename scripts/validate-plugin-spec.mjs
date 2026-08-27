#!/usr/bin/env node
// Every packaging manifest against the spec that reads it: the Claude catalog,
// Agent Plugins v1, and the Codex plugin and marketplace manifests. Much of
// this is what `claude plugin validate` passes clean.
//
// Owns packaging. SKILL.md frontmatter belongs to validate-skill-spec.mjs.
//
// Usage: node scripts/validate-plugin-spec.mjs

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = process.cwd()
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

// --- Claude: the catalog against what is actually on disk ---
const CATALOG = '.claude-plugin/marketplace.json'
const SOURCE_RE = /^\.\/plugins\/([^./][^/]*)$/
const claudeCatalog = readJson(CATALOG)
let catalogEntries = 0

if (claudeCatalog === null) {
  err(`${CATALOG} is missing, so no Claude Code user can install any of this`)
} else if (claudeCatalog) {
  const entries = Array.isArray(claudeCatalog.plugins) ? claudeCatalog.plugins : []
  catalogEntries = entries.length
  const listed = new Set()
  const seenNames = new Set()
  const seenDirs = new Set()

  for (const entry of entries) {
    const name = entry?.name ?? 'unnamed'
    if (seenNames.has(name)) {
      err(`${CATALOG}: duplicate plugin name "${name}"`)
    } else {
      seenNames.add(name)
    }

    const source = String(entry?.source ?? '')
    const match = SOURCE_RE.exec(source)
    if (source.includes('..') || !match) {
      err(`${CATALOG} ${name}: source "${source}" must be "./plugins/<name>"`)
      continue
    }
    const dirName = match[1]
    if (seenDirs.has(dirName)) {
      err(`${CATALOG}: duplicate source "${source}"`)
      continue
    }
    seenDirs.add(dirName)
    listed.add(dirName)

    const manifest = `${source}/.claude-plugin/plugin.json`
    if (!existsSync(join(ROOT, source, '.claude-plugin', 'plugin.json'))) {
      err(`${CATALOG} ${name}: "${source}" has no .claude-plugin/plugin.json`)
      continue
    }
    const declared = readJson(manifest)?.name
    if (declared !== undefined && declared !== name) {
      err(`${manifest}: name "${declared}" != catalog entry "${name}"`)
    }

    if (dirs(join(ROOT, source, 'skills')).length === 0) {
      err(`${source}: no skills, so this plugin installs but does nothing`)
    }
  }

  for (const dir of dirs(join(ROOT, 'plugins'))) {
    if (!listed.has(dir)) {
      err(`${CATALOG}: plugins/${dir} is in the repo but listed by no entry, so it never ships`)
    }
  }
}

// --- Agent Plugins v1: https://agent-plugins.org/specification ---
// The schema sets additionalProperties to false, so a field that is fine in the
// Claude or Codex manifest (displayName, skills) is a hard failure here.
const AGENT_PLUGIN_SCHEMA = 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
const AGENT_PLUGIN_KEYS = new Set([
  '$schema', 'name', 'version', 'description',
  'author', 'homepage', 'repository', 'license', 'keywords', 'extensions',
])
const AGENT_PLUGIN_AUTHOR_KEYS = new Set(['name', 'email', 'url'])
const AGENT_PLUGIN_NAME_RE = /^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/

for (const plugin of dirs(join(ROOT, 'plugins'))) {
  const rel = `plugins/${plugin}/plugin.json`
  const manifest = readJson(rel)
  if (manifest === null) {
    err(`plugins/${plugin}: no plugin.json, so clients reading the Agent Plugins spec do not see this plugin`)
    continue
  }
  if (manifest === undefined) continue

  if (manifest.$schema !== AGENT_PLUGIN_SCHEMA) {
    err(`${rel}: "$schema" must be "${AGENT_PLUGIN_SCHEMA}", got ${JSON.stringify(manifest.$schema)}`)
  }
  if (!manifest.name) {
    err(`${rel}: "name" is required`)
  } else if (manifest.name !== plugin) {
    err(`${rel}: name "${manifest.name}" != directory "${plugin}"`)
  } else if (!AGENT_PLUGIN_NAME_RE.test(manifest.name)) {
    err(`${rel}: "name" does not match the spec's pattern`)
  }

  for (const key of Object.keys(manifest)) {
    if (!AGENT_PLUGIN_KEYS.has(key)) {
      err(`${rel}: "${key}" is not in the Agent Plugins schema, which sets additionalProperties to false — put client-specific data under "extensions"`)
    }
  }
  for (const key of Object.keys(manifest.author ?? {})) {
    if (!AGENT_PLUGIN_AUTHOR_KEYS.has(key)) {
      err(`${rel}: "author.${key}" is not in the Agent Plugins schema`)
    }
  }

  if (!existsSync(join(ROOT, 'plugins', plugin, 'skills'))) {
    err(`${rel}: no sibling skills/ directory, and the spec discovers skills there`)
  }
}

// --- Codex: one plugin manifest per plugin, agreeing with the Claude one ---
for (const plugin of dirs(join(ROOT, 'plugins'))) {
  const rel = `plugins/${plugin}/.codex-plugin/plugin.json`
  const codex = readJson(rel)
  if (codex === null) {
    err(`plugins/${plugin}: no .codex-plugin/plugin.json, so Codex falls back to synthesized metadata instead of what we shipped`)
    continue
  }
  if (codex === undefined) continue

  // Codex requires "version" too; validate-versions.mjs owns every version check.
  for (const field of ['name', 'description']) {
    if (!codex[field]) err(`${rel}: "${field}" is required by Codex`)
  }
  if (codex.name && codex.name !== plugin) {
    err(`${rel}: name "${codex.name}" != directory "${plugin}"`)
  }
  if (codex.skills !== './skills/') {
    err(`${rel}: expected "skills": "./skills/", got ${JSON.stringify(codex.skills)}`)
  }

  // Codex reads presentation metadata from `interface`. At the top level it
  // parses fine and is simply never read, so fail on placement, not absence.
  const codexInterface = codex.interface ?? {}
  for (const field of ['displayName', 'shortDescription', 'longDescription', 'category']) {
    if (codex[field] !== undefined) {
      err(`${rel}: "${field}" is an interface field — move it under "interface", where Codex actually reads it`)
    }
  }
  if (!codexInterface.displayName) {
    err(`${rel}: "interface.displayName" is missing, so install surfaces show the bare plugin name`)
  }

  // Three manifests describe one plugin. Pin the fields a customer sees.
  const claude = readJson(`plugins/${plugin}/.claude-plugin/plugin.json`)
  if (claude) {
    for (const field of ['description', 'license', 'homepage']) {
      if (claude[field] !== undefined && claude[field] !== codex[field]) {
        err(`plugins/${plugin}: "${field}" differs between the Claude and Codex manifests (${JSON.stringify(claude[field])} vs ${JSON.stringify(codex[field])})`)
      }
    }
    // Claude keeps displayName at the top level; Codex nests it. Same string.
    if (claude.displayName !== undefined && claude.displayName !== codexInterface.displayName) {
      err(`plugins/${plugin}: "displayName" differs between the Claude manifest and Codex "interface" (${JSON.stringify(claude.displayName)} vs ${JSON.stringify(codexInterface.displayName)})`)
    }
  }
  const portable = readJson(`plugins/${plugin}/plugin.json`)
  if (portable) {
    for (const field of ['description', 'license', 'homepage', 'repository']) {
      if (portable[field] !== undefined && claude?.[field] !== undefined && portable[field] !== claude[field]) {
        err(`plugins/${plugin}: "${field}" differs between plugin.json and the Claude manifest (${JSON.stringify(portable[field])} vs ${JSON.stringify(claude[field])})`)
      }
    }
  }
}

// --- Codex: the native marketplace must list what the Claude one lists ---
const codexCatalog = readJson('.agents/plugins/marketplace.json')

if (codexCatalog === null) {
  err('.agents/plugins/marketplace.json is missing, so `codex plugin marketplace add` relies on the legacy .claude-plugin path')
} else if (codexCatalog && claudeCatalog) {
  const claudeNames = new Set((claudeCatalog.plugins ?? []).map((p) => p?.name))
  const codexNames = new Set()

  for (const entry of codexCatalog.plugins ?? []) {
    const name = entry?.name ?? 'unnamed'
    codexNames.add(name)

    // Codex resolves source.path against the marketplace root, which for a
    // manifest at .agents/plugins/ is the repo root.
    const path = entry?.source?.path
    if (entry?.source?.source !== 'local') {
      err(`.agents/plugins/marketplace.json ${name}: expected source.source "local", got ${JSON.stringify(entry?.source?.source)}`)
    }
    if (path === './') {
      err(`.agents/plugins/marketplace.json ${name}: Codex does not discover a plugin whose source.path is the marketplace root`)
    } else if (path !== `./plugins/${name}`) {
      err(`.agents/plugins/marketplace.json ${name}: source.path must be "./plugins/${name}", got ${JSON.stringify(path)}`)
    }
  }

  for (const name of claudeNames) {
    if (!codexNames.has(name)) err(`.agents/plugins/marketplace.json: "${name}" is in the Claude catalog but not this one, so Codex users never see it`)
  }
  for (const name of codexNames) {
    if (!claudeNames.has(name)) err(`${CATALOG}: "${name}" is in the Codex catalog but not this one`)
  }
}

for (const e of errors) console.log(`  ERROR  ${e}`)
if (errors.length) {
  console.log(`\n${errors.length} error(s). Not ready to publish.`)
  process.exit(1)
}
console.log(`${catalogEntries} plugin(s); Claude + Agent Plugins + Codex manifests OK.`)
