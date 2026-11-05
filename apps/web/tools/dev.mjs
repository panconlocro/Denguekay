import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const targets = { 'demo-v2': 'http://127.0.0.1:18001', fixtures: 'http://127.0.0.1:18000' };
const [source, ...args] = process.argv.slice(2);
if (!Object.hasOwn(targets, source)) throw new Error('Choose demo-v2 or fixtures.');
const vite = join(
  dirname(createRequire(import.meta.url).resolve('vite/package.json')),
  'bin/vite.js',
);
const child = spawn(process.execPath, [vite, '--host', '127.0.0.1', ...args], {
  stdio: 'inherit',
  env: {
    ...process.env,
    API_PROXY_TARGET: targets[source],
    VITE_API_BASE_URL: '/api/v1',
    VITE_DATA_SOURCE: source,
  },
});
child.on('exit', (code) => process.exit(code ?? 1));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
