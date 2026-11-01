import { describe, expect, it } from 'vitest';
import { DEFAULT_API_BASE, normalizeApiBase, resolveConfig, toWsBase } from './config';

describe('resolveConfig', () => {
  it('reads api and token from the page query', () => {
    const c = resolveConfig('?api=http://127.0.0.1:8761&token=dev');
    expect(c.apiBase).toBe('http://127.0.0.1:8761');
    expect(c.wsBase).toBe('ws://127.0.0.1:8761');
    expect(c.token).toBe('dev');
    expect(c.source).toEqual({ api: 'query', token: 'query' });
  });

  it('falls back to the Vite env, then to the default', () => {
    const env = { VITE_ARGOS_API: 'http://192.168.1.20:9000/', VITE_ARGOS_TOKEN: 'from-env' };
    const c = resolveConfig('', env);
    expect(c.apiBase).toBe('http://192.168.1.20:9000');
    expect(c.token).toBe('from-env');
    expect(c.source).toEqual({ api: 'env', token: 'env' });

    const d = resolveConfig('', {});
    expect(d.apiBase).toBe(DEFAULT_API_BASE);
    expect(d.apiBase).toBe('http://127.0.0.1:8742');
    expect(d.wsBase).toBe('ws://127.0.0.1:8742');
    expect(d.token).toBe('');
    expect(d.source).toEqual({ api: 'default', token: 'default' });
  });

  it('resolves api and token independently', () => {
    const c = resolveConfig('?token=q', { VITE_ARGOS_API: 'http://10.0.0.2:8742' });
    expect(c.apiBase).toBe('http://10.0.0.2:8742');
    expect(c.token).toBe('q');
    expect(c.source).toEqual({ api: 'env', token: 'query' });
  });

  it('query wins over env', () => {
    const c = resolveConfig('?api=http://localhost:1&token=a', {
      VITE_ARGOS_API: 'http://localhost:2',
      VITE_ARGOS_TOKEN: 'b',
    });
    expect(c.apiBase).toBe('http://localhost:1');
    expect(c.token).toBe('a');
  });

  it('ignores unusable api values and blank tokens', () => {
    for (const bad of ['', '   ', 'not a url', 'ftp://host:21', 'javascript:alert(1)', 'file:///etc']) {
      const c = resolveConfig(`?api=${encodeURIComponent(bad)}&token=%20%20`, {});
      expect(c.apiBase).toBe(DEFAULT_API_BASE);
      expect(c.source.api).toBe('default');
      expect(c.token).toBe('');
    }
  });

  it('ignores a remote api from the query unless the token comes with it', () => {
    const env = { VITE_ARGOS_TOKEN: 'secret' };
    const c = resolveConfig('?api=http://attacker.example:8742', env);
    expect(c.apiBase).toBe(DEFAULT_API_BASE); // the env token never leaves the machine
    expect(c.token).toBe('secret');
    const d = resolveConfig('?api=http://localhost:9000', env);
    expect(d.apiBase).toBe('http://localhost:9000');
    const e = resolveConfig('?api=http://10.0.0.2:8742&token=q', env);
    expect(e.apiBase).toBe('http://10.0.0.2:8742');
  });

  it('decodes URL-encoded tokens (token_urlsafe never needs it, but a browser may)', () => {
    expect(resolveConfig('?token=a%2Bb%3D').token).toBe('a+b=');
    expect(resolveConfig('?token=Xy_-9').token).toBe('Xy_-9');
  });
});

describe('normalizeApiBase / toWsBase', () => {
  it('keeps scheme, host and port only', () => {
    expect(normalizeApiBase('http://127.0.0.1:8742/')).toBe('http://127.0.0.1:8742');
    expect(normalizeApiBase('http://127.0.0.1:8742/api/health?x=1#y')).toBe('http://127.0.0.1:8742');
    expect(normalizeApiBase(' https://argos.local ')).toBe('https://argos.local');
    expect(normalizeApiBase(null)).toBeNull();
  });

  it('maps http->ws and https->wss', () => {
    expect(toWsBase('http://127.0.0.1:8742')).toBe('ws://127.0.0.1:8742');
    expect(toWsBase('https://argos.local')).toBe('wss://argos.local');
  });
});
