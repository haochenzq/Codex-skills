import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { constants, copyFileSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const events = ['UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'Interrupt']

function installedNodePath() {
  const executable = realpathSync.native(process.execPath)
  if (process.platform !== 'win32' || !executable.includes(' ')) return executable
  const command = join(process.env.SystemRoot, 'System32', 'cmd.exe')
  const args = ['/d', '/v:off', '/u', '/c', 'for %I in ("%DSH_CODEX_SETUP_NODE%") do @echo %~sI']
  const short = execFileSync(command, args, { encoding: 'utf16le', windowsHide: true,
    windowsVerbatimArguments: true, env: { ...process.env, DSH_CODEX_SETUP_NODE: executable } }).trim()
  if (!short || realpathSync.native(short).toLowerCase() !== executable.toLowerCase()) {
    throw new Error('Could not resolve the installed Node executable.')
  }
  return short
}

export function configureHooks(file, script, executable = installedNodePath()) {
  const path = script.replaceAll('\\', '/')
  const node = executable.replaceAll('\\', '/')
  if (/["`$%!\r\n]/.test(path + node)) throw new Error('Use installation paths without shell expansion characters.')
  const command = (/^[\w:.~/\-]+$/.test(node) ? node : '"' + node + '"') + ' "' + path + '"'
  let original
  try {
    original = readFileSync(file, 'utf8')
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const root = original === undefined ? {} : JSON.parse(original.replace(/^\uFEFF/, ''))
  if (!root || typeof root !== 'object' || Array.isArray(root)) throw new Error('Expected a hooks.json object.')
  if (root.hooks === undefined) root.hooks = {}
  if (!root.hooks || typeof root.hooks !== 'object' || Array.isArray(root.hooks)) throw new Error('Expected a hooks object.')
  let changed = false
  for (const event of events) {
    if (root.hooks[event] === undefined) root.hooks[event] = []
    const groups = root.hooks[event]
    if (!Array.isArray(groups)) throw new Error('Expected hook groups for ' + event)
    const existing = groups.some(group => !group.matcher && group.hooks.some(hook => {
      if (hook.type !== 'command' || hook.async || hook.commandWindows) return false
      const match = /^(?:"[^"]*[\\/]node\.exe"|\S*[\\/]node\.exe|node(?:\.exe)?)\s+"([^"]+)"$/i.exec(hook.command)
      if (!match || match[1].replaceAll('\\', '/').toLowerCase() !== path.toLowerCase()) return false
      if (hook.command !== command) {
        hook.command = command
        changed = true
      }
      return true
    }))
    if (!existing) {
      groups.push({ hooks: [{ type: 'command', command, timeout: 6 }] })
      changed = true
    }
  }
  if (!changed) return
  mkdirSync(dirname(file), { recursive: true })
  const temporary = file + '.' + randomUUID() + '.tmp'
  try {
    writeFileSync(temporary, JSON.stringify(root, null, 2) + '\n', { flag: 'wx', mode: 0o600 })
    if (original === undefined) {
      copyFileSync(temporary, file, constants.COPYFILE_EXCL)
    } else {
      if (readFileSync(file, 'utf8') !== original) throw new Error('hooks.json changed during setup. Run setup again.')
      const backup = file + '.' + randomUUID() + '.bak'
      copyFileSync(file, backup, constants.COPYFILE_EXCL)
      renameSync(temporary, file)
      return backup
    }
  } finally {
    rmSync(temporary, { force: true })
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const home = process.env.CODEX_HOME || join(homedir(), '.codex')
  const file = join(home, 'hooks.json')
  const backup = configureHooks(file, fileURLToPath(new URL('./turn-channel.js', import.meta.url)))
  if (backup) console.log('Previous configuration saved to', backup)
  console.log('Review the five Codex bridge hooks using /hooks:', file)
}
