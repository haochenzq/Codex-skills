import { cp, lstat, mkdir, readdir, rmdir } from 'node:fs/promises';
import { dirname, isAbsolute, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const argument = process.argv[2];
if (!argument || !isAbsolute(argument)) {
  console.error('用法: node create-project.mjs <新项目绝对路径>');
  process.exit(1);
}
const target = resolve(argument);
const template = fileURLToPath(new URL('../assets/template/', import.meta.url));
try {
  await lstat(target);
  throw new Error(`目标已存在，未写入: ${target}`);
} catch (error) {
  if (error.code !== 'ENOENT') { console.error(error.message); process.exit(1); }
}
await mkdir(dirname(target), { recursive: true });
// Atomic reservation prevents overwriting a directory created between check and copy.
await mkdir(target);
try {
  for (const entry of await readdir(template)) {
    await cp(join(template, entry), join(target, entry), { recursive: true, force: false, errorOnExist: true });
  }
  console.log(`已创建: ${target}\n进入目录后执行 npm ci --no-fund，再执行 npm run dev。`);
} catch (error) {
  // Keep partially copied files for inspection; only remove an empty reservation.
  if ((await readdir(target)).length === 0) await rmdir(target);
  throw error;
}
