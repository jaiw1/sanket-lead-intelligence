import { describe, expect, it } from 'vitest'
import { routerBasename } from './basepath'

describe('routerBasename', () => {
  it.each([
    ['/', '/'],
    ['./', '/'],
    ['.', '/'],
    [undefined, '/'],
    ['/drishti/', '/drishti'],
    ['/sanket/', '/sanket'],
    ['drishti', '/drishti'],
  ])('%s -> %s', (base, expected) => {
    expect(routerBasename(base)).toBe(expected)
  })
})
