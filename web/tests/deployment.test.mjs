import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import { frontendConfig, sameOrigin } from '../server-config.mjs'

const secret = 'synthetic-proxy-secret-for-tests-only'
const deployed = { VERCEL: '1', AMIGA_BACKEND_ORIGIN: 'https://api.amiga.test',
  AMIGA_PUBLIC_BASE_URL: 'https://amiga.test', AMIGA_PROXY_SECRET: secret }

test('local demos retain their loopback destination without deployment variables', () => {
  assert.deepEqual(frontendConfig({}), { backendOrigin: 'http://127.0.0.1:8787', publicOrigin: null, proxySecret: '' })
  assert.equal(sameOrigin('http://127.0.0.1:3000', '127.0.0.1:3000', null), true)
  assert.equal(sameOrigin('http://arbitrary.test', 'arbitrary.test', null), false)
})

test('deployed configuration requires separate HTTPS origins and a private proxy secret', () => {
  assert.equal(frontendConfig(deployed).backendOrigin, 'https://api.amiga.test')
  for (const change of [
    { AMIGA_BACKEND_ORIGIN: '' }, { AMIGA_BACKEND_ORIGIN: 'http://api.amiga.test' },
    { AMIGA_BACKEND_ORIGIN: 'https://localhost' }, { AMIGA_BACKEND_ORIGIN: 'https://amiga.test' },
    { AMIGA_BACKEND_ORIGIN: 'https://user:password@api.amiga.test' },
    { AMIGA_BACKEND_ORIGIN: 'https://api.amiga.test/path' },
    { AMIGA_BACKEND_ORIGIN: 'https://api.amiga.test/?query=1' },
    { AMIGA_PUBLIC_BASE_URL: '' }, { AMIGA_PUBLIC_BASE_URL: 'http://amiga.test' },
    { AMIGA_PROXY_SECRET: '' }, { AMIGA_PROXY_SECRET: 'too-short' },
  ]) assert.throws(() => frontendConfig({ ...deployed, ...change }))
})

test('browser origins must match the configured origin, protocol, port and actual Host', () => {
  assert.equal(sameOrigin('https://amiga.test', 'amiga.test', 'https://amiga.test'), true)
  for (const [origin, host] of [
    ['http://amiga.test', 'amiga.test'], ['https://amiga.test:444', 'amiga.test'],
    ['https://attacker.test', 'amiga.test'], ['https://amiga.test', 'attacker.test'],
    ['https://amiga.test.attacker.test', 'amiga.test'], ['null', 'amiga.test'],
    ['https://user@amiga.test', 'amiga.test'], ['https://amiga.test/path', 'amiga.test'],
  ]) assert.equal(sameOrigin(origin, host, 'https://amiga.test'), false)
})

const require = createRequire(new URL('../proxy.ts', import.meta.url))
const { NextRequest } = require('next/server')
const output = ts.transpileModule(readFileSync(new URL('../proxy.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const exports = {}
vm.runInNewContext(output, { exports, require, process, Headers })

function withEnv(values, run) {
  const keys = Object.keys(deployed)
  const saved = Object.fromEntries(keys.map(key => [key, process.env[key]]))
  try {
    for (const key of keys) {
      if (values[key] === undefined) delete process.env[key]
      else process.env[key] = values[key]
    }
    run()
  } finally {
    for (const key of keys) {
      if (saved[key] === undefined) delete process.env[key]
      else process.env[key] = saved[key]
    }
  }
}

test('HTTPS writes keep cookie and CSRF, preserve approved Origin and replace a forged secret', () => withEnv(deployed, () => {
  const response = exports.proxy(new NextRequest('https://amiga.test/api/v1/logout', {
    method: 'POST', headers: { host: 'amiga.test', origin: 'https://amiga.test',
      cookie: 'amiga_session=synthetic-session', 'x-csrf-token': 'synthetic-csrf', 'x-amiga-proxy-secret': 'forged' },
  }))
  assert.equal(response.status, 200)
  for (const [key, value] of Object.entries({ origin: 'https://amiga.test', cookie: 'amiga_session=synthetic-session',
    'x-csrf-token': 'synthetic-csrf', 'x-amiga-proxy-secret': secret })) {
    assert.equal(response.headers.get(`x-middleware-request-${key}`), value)
  }
  assert.equal(response.headers.get('x-amiga-proxy-secret'), null)
}))

test('an attacker cannot forge a public Origin through forwarded Host headers', () => withEnv(deployed, () => {
  const response = exports.proxy(new NextRequest('https://attacker.test/api/v1/login', {
    method: 'POST', headers: { host: 'attacker.test', origin: 'https://amiga.test', 'x-forwarded-host': 'amiga.test' },
  }))
  assert.equal(response.status, 403)
  assert.equal(response.headers.get('x-middleware-request-x-amiga-proxy-secret'), null)
}))

test('reads and origin-less scripts receive the upstream secret for all backend surfaces', () => withEnv(deployed, () => {
  assert.deepEqual(Array.from(exports.config.matcher), ['/api/v1/:path*', '/review', '/static/:path*', '/verifikasi/:path*'])
  for (const path of ['/api/v1/session', '/review', '/static/app.js', '/verifikasi/synthetic']) {
    const response = exports.proxy(new NextRequest('https://amiga.test' + path, { headers: { host: 'amiga.test' } }))
    assert.equal(response.headers.get('x-middleware-request-x-amiga-proxy-secret'), secret)
  }
}))

test('local writes retain the original backend origin and strip visitor-supplied secrets', () => withEnv({}, () => {
  const response = exports.proxy(new NextRequest('http://127.0.0.1:3000/api/v1/login', {
    method: 'POST', headers: { host: '127.0.0.1:3000', origin: 'http://127.0.0.1:3000', 'x-amiga-proxy-secret': 'forged' },
  }))
  assert.equal(response.headers.get('x-middleware-request-origin'), 'http://127.0.0.1:8787')
  assert.equal(response.headers.get('x-middleware-request-x-amiga-proxy-secret'), null)
}))
