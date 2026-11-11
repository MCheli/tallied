import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Tallied as an iPhone Home Screen web app: the manifest and icons in public/ are copied into the
 * build as-is and served from the site root. iOS reads apple-touch-icon for the Home Screen icon
 * and the manifest for name, start URL, scope and standalone display.
 */

const frontend = path.resolve(import.meta.dirname, '..')
const publicDir = path.join(frontend, 'public')

function pngSize(file: string): [number, number] {
  const buf = readFileSync(file)
  expect(buf.subarray(1, 4).toString('ascii')).toBe('PNG')
  return [buf.readUInt32BE(16), buf.readUInt32BE(20)]
}

function pngHasAlpha(file: string): boolean {
  const colourType = readFileSync(file)[25]
  return colourType === 4 || colourType === 6
}

describe('home screen web app', () => {
  const manifest = JSON.parse(readFileSync(path.join(publicDir, 'manifest.webmanifest'), 'utf8'))
  const indexHtml = readFileSync(path.join(frontend, 'index.html'), 'utf8')

  it('opens standalone at the dashboard, scoped to the whole site', () => {
    expect(manifest.name).toBe('Tallied')
    expect(manifest.short_name).toBe('Tallied')
    expect(manifest.display).toBe('standalone')
    expect(manifest.start_url).toBe('/')
    expect(manifest.scope).toBe('/')
  })

  it('lists icons that exist at the sizes they claim', () => {
    expect(manifest.icons.length).toBeGreaterThanOrEqual(2)
    for (const icon of manifest.icons) {
      const file = path.join(publicDir, icon.src)
      expect(existsSync(file), icon.src).toBe(true)
      const [w, h] = pngSize(file)
      expect(`${w}x${h}`).toBe(icon.sizes)
    }
    expect(manifest.icons.some((i: { purpose?: string }) => i.purpose === 'maskable')).toBe(true)
  })

  it('links the manifest and a 180px opaque apple-touch-icon from index.html', () => {
    expect(indexHtml).toContain('<link rel="manifest" href="/manifest.webmanifest" />')
    expect(indexHtml).toContain('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
    expect(indexHtml).toContain('<meta name="apple-mobile-web-app-title" content="Tallied" />')
    const touchIcon = path.join(publicDir, 'apple-touch-icon.png')
    expect(pngSize(touchIcon)).toEqual([180, 180])
    // iOS fills transparent pixels with black, so the icon must be opaque.
    expect(pngHasAlpha(touchIcon)).toBe(false)
  })
})
