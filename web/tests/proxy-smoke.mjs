// Real Next.js -> TLS FastAPI proxy smoke test. Uses synthetic sessions and no DB/worker.
// Supply AMIGA_TEST_TLS_CERT / AMIGA_TEST_TLS_KEY with a localhost/127.0.0.1 test certificate.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https'
import { fileURLToPath } from 'node:url'
import { setTimeout as pause } from 'node:timers/promises'

const root = fileURLToPath(new URL('../../', import.meta.url))
const web = fileURLToPath(new URL('../', import.meta.url))
const certPath = process.env.AMIGA_TEST_TLS_CERT
const keyPath = process.env.AMIGA_TEST_TLS_KEY
assert.ok(certPath && keyPath, 'Supply a test TLS certificate and private key.')
const cert = readFileSync(certPath)
const key = readFileSync(keyPath)
const secret = 'synthetic-proxy-secret-for-smoke-only'
const children = []
let logs = ''

async function freePort() {
  const server = http.createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

function child(command, args, cwd, env) {
  const process = spawn(command, args, { cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
  children.push(process)
  for (const stream of [process.stdout, process.stderr]) stream.on('data', data => { logs = (logs + data).slice(-7000) })
  return process
}

function request(port, path, { method = 'GET', headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    // TLS peer is the local gateway/backend; HTTP Host models the public Vercel host.
    const outgoing = https.request({ hostname: '127.0.0.1', servername: 'localhost', port, path, method, ca: cert, headers,
      timeout: 30_000 }, response => {
      const chunks = []
      response.on('data', chunk => chunks.push(chunk))
      response.on('error', reject)
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers,
        body: Buffer.concat(chunks).toString() }))
    })
    outgoing.on('error', reject)
    outgoing.on('timeout', () => outgoing.destroy(new Error('Proxy smoke request timed out.')))
    if (body) outgoing.write(body)
    outgoing.end()
  })
}

async function ready(check) {
  const end = Date.now() + 50_000
  let lastError
  while (Date.now() < end) {
    try { if (await check()) return } catch (error) { lastError = error }
    if (children.some(child => child.exitCode !== null)) throw new Error('A smoke server exited early.')
    await pause(350)
  }
  throw new Error('Smoke server startup timed out.', { cause: lastError })
}

const backendPort = await freePort()
const frontendPort = await freePort()
const python = process.env.AMIGA_TEST_PYTHON || root + (process.platform === 'win32' ? '/.venv/Scripts/python.exe' : '/.venv/bin/python')
let gateway
try {
  child(python, ['-u', '-c', `
import os, uvicorn
from app.settings import Settings
from app.tests.test_vercel_proxy import synthetic_app
api, _ = synthetic_app(Settings('unused', 'unused', public_base_url='https://amiga.test',
    proxy_secret=os.environ['AMIGA_PROXY_SECRET'], secure_cookies=True))
uvicorn.run(api, host='127.0.0.1', port=${backendPort}, lifespan='off', access_log=False,
    ssl_keyfile=os.environ['AMIGA_TEST_TLS_KEY'], ssl_certfile=os.environ['AMIGA_TEST_TLS_CERT'])
`], root, { ...process.env, AMIGA_PROXY_SECRET: secret })
  await ready(async () => (await request(backendPort, '/api/v1/health',
    { headers: { 'x-amiga-proxy-secret': secret } })).status === 200)

  const nextEnv = { ...process.env, VERCEL: '0', AMIGA_BACKEND_ORIGIN: `https://127.0.0.1:${backendPort}`,
    AMIGA_PUBLIC_BASE_URL: 'https://amiga.test', AMIGA_PROXY_SECRET: secret, NODE_EXTRA_CA_CERTS: certPath }
  child(process.execPath, [web + '/node_modules/next/dist/bin/next', 'dev', '-H', '127.0.0.1', '-p', String(frontendPort)], web, nextEnv)

  // Model Vercel's HTTPS termination while retaining the configured public Host.
  gateway = https.createServer({ key, cert }, (incoming, response) => {
    const upstream = http.request({ hostname: '127.0.0.1', port: frontendPort, path: incoming.url,
      method: incoming.method, headers: incoming.headers }, result => {
      response.writeHead(result.statusCode, result.headers)
      result.pipe(response)
    })
    upstream.on('error', () => { response.writeHead(502); response.end('Starting') })
    incoming.pipe(upstream)
  })
  await new Promise(resolve => gateway.listen(0, '127.0.0.1', resolve))
  const port = gateway.address().port
  const browser = { host: 'amiga.test', origin: 'https://amiga.test' }
  await ready(async () => (await request(port, '/api/v1/health', { headers: browser })).status === 200)

  let checks = 0
  async function expect(path, status, options = {}) {
    const response = await request(port, path, { ...options, headers: { ...browser, ...options.headers } })
    assert.equal(response.status, status, `${path}: ${response.body.slice(0, 120)}`)
    assert.ok(!JSON.stringify(response).includes(secret), 'Proxy secret leaked to the client.')
    checks++
    return response
  }
  assert.equal((await request(backendPort, '/api/v1/health')).status, 403); checks++
  await expect('/', 200)
  await expect('/api/v1/session', 401)
  const login = { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: 'synthetic@amiga.test', password: 'synthetic-only' }) }
  await expect('/api/v1/login', 403, { ...login, headers: { ...login.headers, origin: 'https://attacker.test' } })
  await expect('/api/v1/login', 403, { ...login, headers: { ...login.headers, host: 'attacker.test', 'x-forwarded-host': 'amiga.test' } })
  const signedIn = await expect('/api/v1/login', 200, login)
  const cookie = signedIn.headers['set-cookie'][0]
  assert.match(cookie, /Secure/); assert.match(cookie, /HttpOnly/); assert.match(cookie, /SameSite=strict/)
  const session = { cookie: cookie.split(';')[0] }
  await expect('/api/v1/session', 200, { headers: session })
  await expect('/review', 200, { headers: session })
  await expect('/static/app.css', 200, { headers: session })
  await expect('/verifikasi/not-a-uuid', 422, { headers: session })
  const denied = await expect('/api/v1/logout', 403, { method: 'POST', headers: session })
  assert.equal(JSON.parse(denied.body).code, 'CSRF_REJECTED')
  await expect('/api/v1/logout', 200, { method: 'POST', headers: {
    ...session, 'x-csrf-token': JSON.parse(signedIn.body).csrf } })
  console.log(JSON.stringify({ result: 'PASS', checks, transport: 'HTTPS -> Next.js -> HTTPS FastAPI',
    storage: 'synthetic sessions; no database, worker, AI or Telegram' }))
} catch (error) {
  console.error(logs.replaceAll(secret, '[redacted]'))
  throw error
} finally {
  if (gateway) { gateway.closeAllConnections(); await new Promise(resolve => gateway.close(resolve)) }
  for (const process of children) process.kill()
}
