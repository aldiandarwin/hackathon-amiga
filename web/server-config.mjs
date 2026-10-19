// Server-only configuration shared by the build rewrites and request proxy.
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]'])

/** @param {string} value @param {string} name */
function origin(value, name) {
  let url
  try { url = new URL(value) } catch { throw new Error(`${name} must be an HTTP(S) origin.`) }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash || value !== value.trim()) {
    throw new Error(`${name} must be an origin without credentials, path, query or fragment.`)
  }
  return url
}

/** @param {Record<string, string | undefined>} [env] */
export function frontendConfig(env = process.env) {
  const vercel = env.VERCEL === '1'
  if (vercel && (!env.AMIGA_BACKEND_ORIGIN || !env.AMIGA_PUBLIC_BASE_URL)) {
    throw new Error('Vercel requires AMIGA_BACKEND_ORIGIN and AMIGA_PUBLIC_BASE_URL.')
  }
  const backend = origin(env.AMIGA_BACKEND_ORIGIN || 'http://127.0.0.1:8787', 'AMIGA_BACKEND_ORIGIN')
  const remote = !LOOPBACK.has(backend.hostname)
  const publicUrl = env.AMIGA_PUBLIC_BASE_URL ? origin(env.AMIGA_PUBLIC_BASE_URL, 'AMIGA_PUBLIC_BASE_URL') : null
  const proxySecret = env.AMIGA_PROXY_SECRET || ''
  if ((remote || vercel) && (backend.protocol !== 'https:' || LOOPBACK.has(backend.hostname))) {
    throw new Error('The deployed backend must use a public HTTPS origin.')
  }
  if ((remote || vercel) && (!publicUrl || publicUrl.protocol !== 'https:' || LOOPBACK.has(publicUrl.hostname))) {
    throw new Error('The deployed frontend requires an explicit public HTTPS AMIGA_PUBLIC_BASE_URL.')
  }
  if ((remote || vercel || proxySecret) && !/^[\x21-\x7e]{32,}$/.test(proxySecret)) {
    throw new Error('AMIGA_PROXY_SECRET must contain at least 32 printable non-space ASCII characters.')
  }
  if (proxySecret && !publicUrl) throw new Error('A proxy secret requires AMIGA_PUBLIC_BASE_URL.')
  if (publicUrl?.origin === backend.origin) throw new Error('Frontend and backend origins must differ to avoid a proxy loop.')
  return { backendOrigin: backend.origin, publicOrigin: publicUrl?.origin || null, proxySecret }
}

/** @param {string} value @param {string | null} host @param {string | null} publicOrigin */
export function sameOrigin(value, host, publicOrigin) {
  try {
    const parsed = origin(value, 'Origin')
    if (publicOrigin) return parsed.origin === publicOrigin && parsed.host === host
    return parsed.protocol === 'http:' && LOOPBACK.has(parsed.hostname) && parsed.host === host
  } catch { return false }
}
