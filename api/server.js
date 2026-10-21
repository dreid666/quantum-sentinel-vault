'use strict';

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');

const PORT = process.env.PORT || 3000;
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || '').split(',').filter(Boolean);

const CAPACITY = 30;
const REFILL_PER_SEC = 5;
const buckets = new Map();

function rateLimiter(req, res, next) {
  const key = req.ip;
  const now = Date.now();
  let b = buckets.get(key);
  if (!b) {
    b = { tokens: CAPACITY, last: now };
    buckets.set(key, b);
  }
  b.tokens = Math.min(CAPACITY, b.tokens + ((now - b.last) / 1000) * REFILL_PER_SEC);
  b.last = now;
  if (b.tokens < 1) {
    res.set('Retry-After', String(Math.ceil((1 - b.tokens) / REFILL_PER_SEC)));
    return res.status(429).json({ error: 'Too Many Requests' });
  }
  b.tokens -= 1;
  return next();
}

setInterval(() => {
  const cutoff = Date.now() - 10 * 60 * 1000;
  for (const [k, v] of buckets) if (v.last < cutoff) buckets.delete(k);
}, 60 * 1000).unref();

const app = express();
app.disable('x-powered-by');

app.use(
  helmet({
    contentSecurityPolicy: {
      useDefaults: false,
      directives: {
        defaultSrc: ["'none'"],
        baseUri: ["'none'"],
        frameAncestors: ["'none'"],
        formAction: ["'none'"],
      },
    },
    referrerPolicy: { policy: 'no-referrer' },
    crossOriginResourcePolicy: { policy: 'same-origin' },
    hsts: { maxAge: 31536000, includeSubDomains: true, preload: true },
  })
);

app.use(
  cors({
    origin(origin, cb) {
      if (!origin || ALLOWED_ORIGINS.includes(origin)) return cb(null, true);
      return cb(new Error('Origin not allowed'));
    },
    methods: ['GET', 'POST'],
    allowedHeaders: ['Content-Type'],
    maxAge: 600,
  })
);

app.use(rateLimiter);
app.use(express.json({ limit: '10kb' }));

app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  const status = err.status || (err.message === 'Origin not allowed' ? 403 : 500);
  res.status(status).json({ error: status === 500 ? 'Internal Server Error' : err.message });
});

if (require.main === module) {
  app.listen(PORT, () => console.log(`API listening on ${PORT}`));
}

module.exports = app;
