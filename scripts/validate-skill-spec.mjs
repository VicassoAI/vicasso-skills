#!/usr/bin/env node
// SKILL.md frontmatter against https://agentskills.io/specification
//
// Owns what makes a directory a skill. Whether a plugin ships any skills is
// packaging, and belongs to validate-plugin-spec.mjs.
//
// Usage: node scripts/validate-skill-spec.mjs

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = process.cwd()
const errors = []
const err = (m) => errors.push(m)

const dirs = (p) =>
  existsSync(p)
    ? readdirSync(p, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name)
    : []

// An out-of-spec key is what makes `gh skill publish` reject a skill.
const SPEC_KEYS = new Set(['name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'])
const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/

// Handles flat scalars only, which is all this repo uses. A nested block is
// recorded as present-but-unread so key checks run without inventing a value.
function parseFrontmatter(text, rel) {
  const lines = text.split(/\r?\n/)
  if (lines[0] !== '---') {
    err(`${rel}: must start with a --- frontmatter block`)
    return null
  }
  const end = lines.indexOf('---', 1)
  if (end === -1) {
    err(`${rel}: frontmatter block is never closed`)
    return null
  }
  const fields = new Map()
  let current = null
  for (const line of lines.slice(1, end)) {
    if (!line.trim()) continue
    if (/^\s/.test(line)) {
      if (current) fields.set(current, null) // nested value, not read
      continue
    }
    const m = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line)
    if (!m) {
      err(`${rel}: cannot parse frontmatter line: ${line.slice(0, 60)}`)
      continue
    }
    current = m[1]
    fields.set(current, m[2].trim())
  }
  return fields
}

function checkSkill(dir, rel) {
  const text = readFileSync(join(ROOT, rel), 'utf8')
  const fields = parseFrontmatter(text, rel)
  if (!fields) return

  for (const key of fields.keys()) {
    if (!SPEC_KEYS.has(key)) {
      err(`${rel}: frontmatter key "${key}" is not in the Agent Skills spec, so agents other than Claude Code may reject this skill`)
    }
  }

  const name = fields.get('name')
  if (name == null) {
    err(`${rel}: "name" is required`)
  } else {
    if (name.length > 64) err(`${rel}: "name" is ${name.length} chars, spec max is 64`)
    if (!NAME_RE.test(name)) err(`${rel}: "name" must be lowercase alphanumerics and single hyphens, got "${name}"`)
    if (name !== dir) err(`${rel}: "name" is "${name}" but the directory is "${dir}" — the spec requires they match`)
  }

  const description = fields.get('description')
  if (description == null) {
    err(`${rel}: "description" is required — without it no agent knows when to load the skill`)
  } else {
    if (!description) err(`${rel}: "description" is empty`)
    if (description.length > 1024) err(`${rel}: "description" is ${description.length} chars, spec max is 1024`)
  }

  const compatibility = fields.get('compatibility')
  if (compatibility != null && compatibility.length > 500) {
    err(`${rel}: "compatibility" is ${compatibility.length} chars, spec max is 500`)
  }
}

let skillCount = 0
for (const plugin of dirs(join(ROOT, 'plugins'))) {
  for (const skill of dirs(join(ROOT, 'plugins', plugin, 'skills'))) {
    const rel = `plugins/${plugin}/skills/${skill}/SKILL.md`
    if (!existsSync(join(ROOT, rel))) {
      err(`plugins/${plugin}/skills/${skill}: no SKILL.md, so this directory is not a skill`)
      continue
    }
    checkSkill(skill, rel)
    skillCount++
  }
}

for (const e of errors) console.log(`  ERROR  ${e}`)
if (errors.length) {
  console.log(`\n${errors.length} error(s). Not ready to publish.`)
  process.exit(1)
}
console.log(`${skillCount} skill(s) match the Agent Skills spec.`)
