import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { configureHooks } from './configure-hooks.js'

test('configure five user hooks without duplicating existing commands or replacing other hooks', t => {
  const directory = mkdtempSync(join(tmpdir(), 'bridge-hooks-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  const file = join(directory, 'hooks.json')
  const script = 'C:/Test Home/packages/0.6.8/turn-channel.js'
  const node = 'C:/PROGRA~1/nodejs/node.exe'
  const other = { matcher: 'Bash', hooks: [{ type: 'command', command: 'existing' }] }
  const previous = { hooks: [{ type: 'command', command: 'node.exe "' + script + '"', timeout: 6 }] }
  const original = JSON.stringify({ name: 'keep', hooks: { PostToolUse: [other, previous] } })
  writeFileSync(file, original)
  const backup = configureHooks(file, script, node)
  assert.equal(readFileSync(backup, 'utf8'), original)
  const installed = readFileSync(file, 'utf8')
  const result = JSON.parse(installed)
  assert.equal(result.name, 'keep')
  assert.equal(result.hooks.PostToolUse.length, 2)
  assert.deepEqual(result.hooks.PostToolUse[0], other)
  assert.equal(Object.keys(result.hooks).length, 5)
  assert.equal(result.hooks.Stop[0].hooks[0].command, node + ' "' + script + '"')
  assert.equal(result.hooks.PostToolUse[1].hooks[0].command, result.hooks.Stop[0].hooks[0].command)
  configureHooks(file, script, node)
  assert.equal(readFileSync(file, 'utf8'), installed)
})
