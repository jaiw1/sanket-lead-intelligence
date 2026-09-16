import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import useIdleTimeout from './useIdleTimeout'

const IDLE = 30 * 60 * 1000
const WARN = 2 * 60 * 1000

const advance = async (ms) => { await act(async () => { vi.advanceTimersByTime(ms) }) }

describe('useIdleTimeout', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('stays quiet while there is time left', async () => {
    const { result } = renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN }))
    await advance(IDLE - WARN - 1000)
    expect(result.current.warning).toBe(false)
  })

  it('warns exactly 2 minutes before the idle limit', async () => {
    const { result } = renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN }))
    await advance(IDLE - WARN)
    expect(result.current.warning).toBe(true)
    expect(result.current.secondsLeft).toBeLessThanOrEqual(120)
    expect(result.current.secondsLeft).toBeGreaterThan(115)
  })

  it('calls onExpire once when the window lapses', async () => {
    const onExpire = vi.fn()
    renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN, onExpire }))
    await advance(IDLE + 2000)
    expect(onExpire).toHaveBeenCalledTimes(1)
    await advance(10_000)
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it('activity before the warning slides the window forward', async () => {
    const onExpire = vi.fn()
    const { result } = renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN, onExpire }))

    await advance(IDLE - WARN - 60_000)
    await act(async () => { window.dispatchEvent(new Event('keydown')) })
    await advance(IDLE - WARN - 60_000)

    expect(result.current.warning).toBe(false)
    expect(onExpire).not.toHaveBeenCalled()
  })

  it('activity does NOT dismiss the warning once it is showing', async () => {
    const { result } = renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN }))
    await advance(IDLE - WARN)
    expect(result.current.warning).toBe(true)

    await act(async () => { window.dispatchEvent(new Event('keydown')) })
    await advance(1000)
    expect(result.current.warning).toBe(true)
  })

  it('"Stay signed in" pings the server and resets the window', async () => {
    const onStayAlive = vi.fn().mockResolvedValue(undefined)
    const onExpire = vi.fn()
    const { result } = renderHook(() => useIdleTimeout({ idleMs: IDLE, warningMs: WARN, onStayAlive, onExpire }))

    await advance(IDLE - WARN)
    expect(result.current.warning).toBe(true)

    await act(async () => { await result.current.stayAlive() })
    expect(onStayAlive).toHaveBeenCalledOnce()
    expect(result.current.warning).toBe(false)

    await advance(WARN + 5000)
    expect(onExpire).not.toHaveBeenCalled()
  })

  it('does nothing at all when disabled', async () => {
    const onExpire = vi.fn()
    const { result } = renderHook(() => useIdleTimeout({ enabled: false, idleMs: IDLE, warningMs: WARN, onExpire }))
    await advance(IDLE * 2)
    expect(onExpire).not.toHaveBeenCalled()
    expect(result.current.warning).toBe(false)
  })
})
