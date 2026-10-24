import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/http.ts', import.meta.url), 'utf8')
  .replace("import { API_BASE_URL } from './config';", "const API_BASE_URL = 'http://test/api';");
const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ES2020 } }).outputText;
const { request, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
globalThis.window = { setTimeout, clearTimeout };

test('API errors preserve fields, conflicts, retry timing and safe recovery messages', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'attendees'], msg: 'Must be at least 1' }] }), { status: 422 });
    await assert.rejects(request('/events'), error => error instanceof ApiError && error.status === 422 && error.fieldErrors.attendees === 'Must be at least 1' && error.message.includes('attendees'));
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'A plan is already running.' }), { status: 409 });
    await assert.rejects(request('/events'), /A plan is already running/);
    globalThis.fetch = async () => new Response('{}', { status: 429, headers: { 'Retry-After': '35' } });
    await assert.rejects(request('/events'), error => error.retryAfter === 35 && error.message.includes('35 seconds'));
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'private-provider-detail' }), { status: 500 });
    await assert.rejects(request('/events'), error => !error.message.includes('private-provider-detail') && error.status === 500);
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
    await assert.rejects(request('/events'), /Could not connect/);
    globalThis.fetch = async () => new Response(null, { status: 204 });
    assert.equal(await request('/cancel'), undefined);
    globalThis.window.setTimeout = fn => setTimeout(fn, 0);
    globalThis.fetch = async (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))));
    await assert.rejects(request('/events'), /Check your event or run status/);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window.setTimeout = setTimeout;
  }
});
