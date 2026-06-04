import { useMutation, useQuery, type QueryKey } from "@tanstack/react-query";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function buildUrl(path: string, params?: Record<string, unknown>) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function requestJson<T>(path: string, init?: RequestInit, params?: Record<string, unknown>): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function useJsonQuery<T>(key: QueryKey, path: string, params?: Record<string, unknown>) {
  return useQuery({ queryKey: key, queryFn: () => requestJson<T>(path, undefined, params) });
}

export const getGetBotStatusQueryKey = () => ["bot-status"] as const;
export const useGetBotStatus = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetBotStatusQueryKey(), "/api/bot/status");

export const getGetBotConfigQueryKey = () => ["bot-config"] as const;
export const useGetBotConfig = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetBotConfigQueryKey(), "/api/bot/config");
export const useUpdateBotConfig = () => useMutation({ mutationFn: ({ data }: { data: unknown }) => requestJson<any>("/api/bot/config", { method: "PUT", body: JSON.stringify(data) }) });

export const getGetMarketsQueryKey = (params?: Record<string, unknown>) => ["markets", params ?? {}] as const;
export const useGetMarkets = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetMarketsQueryKey(params), "/api/markets", params);

export const getGetPositionsQueryKey = () => ["positions"] as const;
export const useGetPositions = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetPositionsQueryKey(), "/api/positions");

export const getGetSignalsQueryKey = (params?: Record<string, unknown>) => ["signals", params ?? {}] as const;
export const useGetSignals = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetSignalsQueryKey(params), "/api/signals", params);

export const getGetTradesQueryKey = (params?: Record<string, unknown>) => ["trades", params ?? {}] as const;
export const useGetTrades = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetTradesQueryKey(params), "/api/trades", params);

export const getGetRiskMetricsQueryKey = () => ["risk"] as const;
export const useGetRiskMetrics = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetRiskMetricsQueryKey(), "/api/risk");

export const getGetPnlSummaryQueryKey = () => ["pnl-summary"] as const;
export const useGetPnlSummary = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetPnlSummaryQueryKey(), "/api/pnl/summary");

export const getGetPnlChartQueryKey = (params?: Record<string, unknown>) => ["pnl-chart", params ?? {}] as const;
export const useGetPnlChart = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetPnlChartQueryKey(params), "/api/pnl/chart", params);

export const getGetDashboardSummaryQueryKey = () => ["dashboard-summary"] as const;
export const useGetDashboardSummary = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetDashboardSummaryQueryKey(), "/api/dashboard/summary");

export const getGetLogsQueryKey = (params?: Record<string, unknown>) => ["logs", params ?? {}] as const;
export const useGetLogs = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetLogsQueryKey(params), "/api/logs", params);

export const getGetPaperPositionsQueryKey = (params?: Record<string, unknown>) => ["paper-positions", params ?? {}] as const;
export const useGetPaperPositions = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetPaperPositionsQueryKey(params), "/api/paper/positions", params);

export const getGetPaperTradesQueryKey = (params?: Record<string, unknown>) => ["paper-trades", params ?? {}] as const;
export const useGetPaperTrades = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetPaperTradesQueryKey(params), "/api/paper/trades", params);

export const getGetPaperStatsQueryKey = () => ["paper-stats"] as const;
export const useGetPaperStats = (_params?: unknown, _options?: unknown) => useJsonQuery<any>(getGetPaperStatsQueryKey(), "/api/paper/stats");

export const getGetPaperChartQueryKey = (params?: Record<string, unknown>) => ["paper-chart", params ?? {}] as const;
export const useGetPaperChart = (params?: Record<string, unknown>, _options?: unknown) => useJsonQuery<any>(getGetPaperChartQueryKey(params), "/api/paper/chart", params);

export const useControlBot = () => useMutation({ mutationFn: ({ data }: { data: unknown }) => requestJson<any>("/api/bot/control", { method: "POST", body: JSON.stringify(data) }) });
