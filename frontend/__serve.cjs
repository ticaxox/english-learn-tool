/**
 * Serve the built dist on a port, proxying /api to the running stack.
 *
 *   node __serve.cjs [port] [apiBase]
 *
 * The backend checks Origin against CORS_ORIGINS, which lists the deployed
 * host, so the proxy rewrites Origin on the way through. That is why this
 * exists instead of `vite preview`: the pages must talk to the real backend.
 */
// Local preview of the built dist, proxying /api to the running stack so the
// pages talk to the same backend the containerised deploy uses.
const http = require('http'), fs = require('fs'), path = require('path')
const root = path.resolve('dist')
const port = Number(process.argv[2] || 5190)
const API = process.argv[3] || 'http://127.0.0.1:9280'
// The backend validates Origin on /auth/refresh against CORS_ORIGINS, which
// lists the deployed host - not the address this proxy happens to dial. Those
// are two different things: the socket goes to $API, the header must be the
// allow-listed value or every token refresh comes back 403.
const ORIGIN = process.env.PREVIEW_ORIGIN || 'http://127.0.0.1:9280'
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript', '.css':'text/css',
  '.png':'image/png', '.svg':'image/svg+xml', '.woff2':'font/woff2', '.ico':'image/x-icon' }
http.createServer((req, res) => {
  if (req.url.startsWith('/api/')) {
    // Backend checks Origin against CORS_ORIGINS; rewrite so the preview is accepted.
    const headers = { ...req.headers, host: '127.0.0.1:9280', origin: ORIGIN }
    const p = http.request(API + req.url, { method: req.method, headers },
      (up) => { res.writeHead(up.statusCode, up.headers); up.pipe(res) })
    p.on('error', () => { res.writeHead(502); res.end('api down') })
    req.pipe(p); return
  }
  let u = decodeURIComponent(req.url.split('?')[0])
  let file = path.join(root, u)
  if (!file.startsWith(root)) { res.writeHead(403); return res.end() }
  fs.stat(file, (e, st) => {
    if (e || !st.isFile()) file = path.join(root, 'index.html')   // SPA fallback
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404); return res.end('not found') }
      res.writeHead(200, { 'content-type': types[path.extname(file)] || 'application/octet-stream' })
      res.end(buf)
    })
  })
}).listen(port, () => console.log(`serving ${root} on ${port}, /api -> ${API}`))
