import { beforeEach, describe, expect, it, vi } from "vitest"

import { scannerApi } from "@/api/scanner"
import { useScannerStore } from "@/stores/scanner-store"
import type { ScanConfig, ScanJob } from "@/types/scanner"

vi.mock("@/api/scanner", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/scanner")>()
  return {
    ...original,
    scannerApi: {
      start: vi.fn(),
      results: vi.fn(),
      cancel: vi.fn(),
      websocketUrl: vi.fn(() => "ws://scan"),
    },
  }
})

class FakeSocket {
  static instances: FakeSocket[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor(readonly url: string) { FakeSocket.instances.push(this) }
  close() { this.closed = true; this.onclose?.() }
  message(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent) }
}

const config = { quote: "USDC", timeframe: "4h" } as ScanConfig
const job = { id: "job-1", status: "running", config, progress: { processed: 0, total: 1, successful: 0, filtered: 0, errors: 0, percent: 0 } } as ScanJob
const indicatorSignals = {
  rsi: {
    status: "available",
    direction: "bullish",
    signal: "exit_oversold",
    state: "near_oversold",
    strength: 0.75,
    reason: "Sortie de survente",
    raw_value: 31.4,
  },
} as const

describe("scanner store", () => {
  beforeEach(() => {
    FakeSocket.instances = []
    vi.stubGlobal("WebSocket", FakeSocket)
    vi.clearAllMocks()
    useScannerStore.setState({ config: null, job: null, results: [], status: "idle", error: null })
  })

  it("fige la configuration du job et récupère les résultats finaux", async () => {
    vi.mocked(scannerApi.start).mockResolvedValue(job)
    vi.mocked(scannerApi.results).mockResolvedValue({ ...job, status: "completed", results: [{ symbol: "BTC/USDC" }] } as ScanJob)
    await useScannerStore.getState().startScan(config)
    expect(useScannerStore.getState()).toMatchObject({ config, job, status: "running" })
    FakeSocket.instances[0].message({ ...job, status: "completed" })
    await vi.waitFor(() => expect(useScannerStore.getState().results).toHaveLength(1))
    expect(useScannerStore.getState().job?.config).toBe(config)
  })

  it("conserve les signaux structurés des résultats finaux", async () => {
    vi.mocked(scannerApi.start).mockResolvedValue(job)
    vi.mocked(scannerApi.results).mockResolvedValue({
      ...job,
      status: "completed",
      results: [{
        symbol: "BTC/USDC",
        timeframe: "1h",
        indicator_signals: indicatorSignals,
      }],
    } as ScanJob)
    await useScannerStore.getState().startScan(config)
    FakeSocket.instances[0].message({ ...job, status: "completed" })
    await vi.waitFor(() => expect(useScannerStore.getState().results).toHaveLength(1))
    expect(useScannerStore.getState().results[0].indicator_signals).toEqual(indicatorSignals)
  })

  it("ferme l’ancien socket avant un nouveau scan", async () => {
    vi.mocked(scannerApi.start).mockResolvedValueOnce(job).mockResolvedValueOnce({ ...job, id: "job-2" })
    await useScannerStore.getState().startScan(config)
    const first = FakeSocket.instances[0]
    await useScannerStore.getState().startScan(config)
    expect(first.closed).toBe(true)
    expect(FakeSocket.instances).toHaveLength(2)
  })

  it("rejette un message WebSocket invalide sans corrompre le job courant", async () => {
    vi.mocked(scannerApi.start).mockResolvedValue(job)
    await useScannerStore.getState().startScan(config)

    FakeSocket.instances[0].message({ id: "job-1", status: "completed" })

    expect(useScannerStore.getState()).toMatchObject({
      job,
      status: "failed",
      error: "Message de progression invalide",
    })
  })
})
