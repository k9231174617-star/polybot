import { useState } from "react";
import {
  useGetDashboardSummary, getGetDashboardSummaryQueryKey,
  useGetPnlChart, getGetPnlChartQueryKey,
  useGetPositions, getGetPositionsQueryKey,
  useGetSignals, getGetSignalsQueryKey,
  useGetLogs, getGetLogsQueryKey,
  useGetRiskMetrics, getGetRiskMetricsQueryKey,
} from "@workspace/api-client-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";

type Period = "1d" | "7d" | "30d" | "all";

function StatCard({ label, value, subValue, positive }: {
  label: string; value: string; subValue?: string; positive?: boolean;
}) {
  return (
    <div className="bg-card border border-border rounded-md p-3 sm:p-4">
      <div className="text-[10px] sm:text-xs text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div className={cn(
        "text-xl sm:text-2xl font-mono font-bold tabular-nums",
        positive === true ? "text-[hsl(var(--success))]" :
        positive === false ? "text-destructive" : "text-foreground"
      )}>{value}</div>
      {subValue && <div className={cn(
        "text-[10px] sm:text-xs font-mono mt-0.5 tabular-nums",
        positive === true ? "text-[hsl(var(--success))]" :
        positive === false ? "text-destructive" : "text-muted-foreground"
      )}>{subValue}</div>}
    </div>
  );
}

function SignalTypeBadge({ type }: { type: string }) {
  const labels: Record<string, string> = {
    price_discrepancy: "PRICE",
    cross_market_arb: "ARB",
    momentum: "MOM",
    sentiment_lag: "SENT",
    implied_prob: "IMP",
    roda_oracle_lag: "Resolution Lag Arb",
    roda_divergence: "RODA DIV",
    lch_cascade: "LCH",
    hybrid_roda_lch_cross: "HYB",
    mss2_spread_capture: "MSS2",
  };
  return (
    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
      {labels[type] ?? type.toUpperCase()}
    </span>
  );
}

export default function Dashboard() {
  const [period, setPeriod] = useState<Period>("7d");
  const { t } = useI18n();

  const { data: summary, isLoading: sumLoading } = useGetDashboardSummary({
    query: { queryKey: getGetDashboardSummaryQueryKey() }
  });
  const { data: chartData, isLoading: chartLoading } = useGetPnlChart({ period }, {
    query: { queryKey: getGetPnlChartQueryKey({ period }) }
  });
  const { data: positions, isLoading: posLoading } = useGetPositions({
    query: { queryKey: getGetPositionsQueryKey() }
  });
  const { data: signals, isLoading: sigLoading } = useGetSignals({ status: "pending" }, {
    query: { queryKey: getGetSignalsQueryKey({ status: "pending" }) }
  });
  const { data: risk } = useGetRiskMetrics({
    query: { queryKey: getGetRiskMetricsQueryKey() }
  });
  const { data: logs } = useGetLogs({ limit: 20, level: "info" }, {
    query: { queryKey: getGetLogsQueryKey({ limit: 20, level: "info" }) }
  });

  const pnlPositive = (summary?.total_pnl ?? 0) >= 0;
  const dailyPositive = (summary?.daily_pnl ?? 0) >= 0;
  const positionsList = positions ?? [];
  const signalsList = signals ?? [];
  const logsList = logs ?? [];
  const reconciliationStatus = String(summary?.balance_reconciliation_status ?? "unknown");
  const reconciliationDeltaUsd = summary?.balance_reconciliation_discrepancy_usd ?? null;
  const reconciliationDeltaPct = summary?.balance_reconciliation_discrepancy_pct ?? null;
  const reconciliationUpdatedAt = summary?.balance_reconciliation_updated_at ?? null;
  const reconciliationIsOk = reconciliationStatus === "ok" || reconciliationStatus === "synced";
  const latencyDecision = summary?.latency_signal_to_decision_ms ?? null;
  const latencyExecution = summary?.latency_decision_to_execution_ms ?? null;
  const latencyTradeRecorded = summary?.latency_signal_to_trade_recorded_ms ?? null;
  const latencyConfirmation = summary?.latency_signal_to_confirmation_ms ?? null;
  const latencyEvents = summary?.latency_events_count ?? 0;
  const errorRate = summary?.error_rate_24h ?? 0;
  const heartbeatAgeSeconds = summary?.heartbeat_age_seconds ?? null;
  const heartbeatStale = Boolean(summary?.heartbeat_stale);
  const droppedSignalsCount = summary?.dropped_signals_count ?? 0;
  const fillSuccessRate = summary?.fill_success_rate ?? 0;
  const hasLatencyDecision = Boolean(latencyDecision && latencyDecision.count > 0);
  const hasLatencyTradeRecorded = Boolean(latencyTradeRecorded && latencyTradeRecorded.count > 0);
  const hasLatencyConfirmation = Boolean(latencyConfirmation && latencyConfirmation.count > 0);
  const heartbeatAgeLabel = heartbeatAgeSeconds !== null
    ? heartbeatAgeSeconds < 60
      ? `${heartbeatAgeSeconds}s`
      : `${Math.floor(heartbeatAgeSeconds / 60)}m`
    : "—";

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
        {sumLoading ? Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        )) : <>
          <StatCard label={t("stat_portfolio")} value={`$${(summary?.portfolio_value_usd ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
          <StatCard label={t("stat_total_pnl")} value={`${pnlPositive ? "+" : ""}$${(summary?.total_pnl ?? 0).toFixed(2)}`}
            subValue={`${pnlPositive ? "+" : ""}${(summary?.total_pnl_pct ?? 0).toFixed(2)}%`} positive={pnlPositive} />
          <StatCard label={t("stat_today_pnl")} value={`${dailyPositive ? "+" : ""}$${(summary?.daily_pnl ?? 0).toFixed(2)}`}
            subValue={`${dailyPositive ? "+" : ""}${(summary?.daily_pnl_pct ?? 0).toFixed(2)}%`} positive={dailyPositive} />
          <StatCard label={t("stat_positions")} value={String(summary?.open_positions_count ?? 0)} />
          <StatCard label={t("stat_signals")} value={String(summary?.pending_signals_count ?? 0)} />
          <StatCard label={t("stat_win_rate")} value={`${((summary?.win_rate ?? 0) * 100).toFixed(1)}%`}
            subValue={`${summary?.trades_today ?? 0} ${t("trades_today")}`} />
        </>}
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t("latency_title")}</div>
        <div className="text-[10px] text-muted-foreground">{latencyEvents} {t("latency_events")}</div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {sumLoading ? Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        )) : <>
          <StatCard
            label={t("latency_signal_to_decision")}
            value={hasLatencyDecision ? `${latencyDecision.p50_ms.toFixed(0)}ms` : "—"}
            subValue={hasLatencyDecision ? `p95 ${latencyDecision.p95_ms.toFixed(0)}ms · n=${latencyDecision.count}` : undefined}
          />
          <StatCard
            label={t("latency_signal_to_trade")}
            value={hasLatencyTradeRecorded ? `${latencyTradeRecorded.p50_ms.toFixed(0)}ms` : "—"}
            subValue={hasLatencyTradeRecorded ? `p95 ${latencyTradeRecorded.p95_ms.toFixed(0)}ms · n=${latencyTradeRecorded.count}` : undefined}
          />
          <StatCard
            label={t("latency_signal_to_confirmation")}
            value={hasLatencyConfirmation ? `${latencyConfirmation.p50_ms.toFixed(0)}ms` : "—"}
            subValue={hasLatencyConfirmation ? `p95 ${latencyConfirmation.p95_ms.toFixed(0)}ms · n=${latencyConfirmation.count}` : undefined}
          />
          <StatCard
            label={t("latency_events")}
            value={String(latencyEvents)}
            subValue={latencyDecision || latencyExecution || latencyConfirmation ? t("latency_title") : undefined}
          />
        </>}
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-5 gap-3">
        {sumLoading ? Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        )) : <>
          <StatCard
            label={t("slo_error_rate")}
            value={`${(errorRate * 100).toFixed(1)}%`}
            subValue={`${summary?.error_events_24h ?? 0} / ${summary?.log_events_24h ?? 0}`}
            positive={errorRate < 0.05}
          />
          <StatCard
            label={t("slo_heartbeat")}
            value={heartbeatAgeLabel}
            subValue={heartbeatStale ? t("slo_heartbeat_stale") : t("slo_heartbeat_fresh")}
            positive={!heartbeatStale}
          />
          <StatCard
            label={t("slo_dropped_signals")}
            value={String(droppedSignalsCount)}
            subValue={t("slo_title")}
            positive={droppedSignalsCount === 0}
          />
          <StatCard
            label={t("slo_fill_success")}
            value={`${(fillSuccessRate * 100).toFixed(1)}%`}
            subValue="orders"
            positive={fillSuccessRate >= 0.9}
          />
          <StatCard
            label={t("slo_reconciliation_drift")}
            value={`${((reconciliationDeltaPct ?? 0) * 100).toFixed(2)}%`}
            subValue={reconciliationDeltaUsd !== null ? `$${Math.abs(reconciliationDeltaUsd).toFixed(2)}` : "—"}
            positive={Math.abs(reconciliationDeltaPct ?? 0) < 0.01}
          />
        </>}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-card border border-border rounded-md p-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("equity_curve")}</span>
            <div className="flex flex-wrap gap-1">
              {(["1d", "7d", "30d", "all"] as Period[]).map((p) => (
                <button key={p} onClick={() => setPeriod(p)}
                  className={cn("text-[10px] sm:text-xs font-mono px-2 py-1 rounded transition-colors border",
                    period === p ? "bg-primary text-primary-foreground border-primary" : "text-muted-foreground border-border hover:text-foreground"
                  )}>
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          {chartLoading ? <Skeleton className="h-48" /> : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={chartData ?? []} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(217,91%,60%)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="hsl(217,91%,60%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  tickFormatter={(v) => new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  tickFormatter={(v) => `$${v}`} axisLine={false} tickLine={false} width={60} />
                <Tooltip
                  contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 4, fontSize: 12 }}
                  labelFormatter={(v) => new Date(v).toLocaleDateString()}
                  formatter={(v: number) => [`$${v.toFixed(2)}`, "P&L"]} />
                <Area type="monotone" dataKey="cumulative_pnl" stroke="hsl(217,91%,60%)" fill="url(#pnlGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="bg-card border border-border rounded-md p-4 flex flex-col min-h-[24rem]">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">{t("live_signals")}</div>
          {sigLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 mb-2" />) : (
            <div className="space-y-2 overflow-y-auto flex-1">
              {signalsList.length === 0 && (
                <div className="text-muted-foreground text-xs text-center py-8">{t("no_pending_signals")}</div>
              )}
              {signalsList.slice(0, 8).map((s) => (
                <div key={s.id} className="border border-border rounded-sm p-2.5 hover:border-primary/40 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <SignalTypeBadge type={s.signal_type} />
                    <span className={cn("text-xs font-mono font-bold", s.direction === "YES" ? "text-[hsl(var(--success))]" : "text-destructive")}>{s.direction}</span>
                    <span className="text-xs font-mono ml-auto text-[hsl(var(--success))] font-bold">
                      +{(s.edge * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground leading-tight line-clamp-1">{s.market_question}</div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-1 text-[10px] font-mono text-muted-foreground">
                    <span>MKT: {(s.market_price * 100).toFixed(1)}%</span>
                    <span className="text-right">MDL: {(s.model_probability * 100).toFixed(1)}%</span>
                    <span>K: ${s.kelly_size_usd.toFixed(0)}</span>
                    <span className="text-right">{(s.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-card border border-border rounded-md">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("open_positions")}</span>
            <span className="text-xs font-mono text-muted-foreground">{positionsList.length} {t("active")}</span>
          </div>
          {posLoading ? <Skeleton className="m-4 h-32" /> : (
            <>
              <div className="md:hidden divide-y divide-border/50">
                {positionsList.length === 0 && (
                  <div className="px-4 py-8 text-center text-muted-foreground text-xs">{t("no_open_positions")}</div>
                )}
                {positionsList.map((p) => (
                  <div key={p.id} className="px-4 py-3 space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm text-foreground">{p.market_question}</div>
                        <div className="text-[10px] text-muted-foreground">{t("col_entry")}: {(p.entry_price * 100).toFixed(1)}¢ · {t("col_now")}: {(p.current_price * 100).toFixed(1)}¢</div>
                      </div>
                      <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0",
                        p.side === "YES" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-destructive/10 text-destructive border-destructive/20"
                      )}>{p.side}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-muted-foreground">
                      <span>{t("col_size")}: <span className="text-foreground tabular-nums">${p.size_usd.toFixed(0)}</span></span>
                      <span className="text-right">{t("col_pnl")}: <span className={cn("font-bold tabular-nums", p.unrealized_pnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}</span></span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="hidden md:block">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-4 py-2 text-left text-muted-foreground font-normal">{t("col_market")}</th>
                      <th className="px-3 py-2 text-right text-muted-foreground font-normal">{t("col_side")}</th>
                      <th className="px-3 py-2 text-right text-muted-foreground font-normal">{t("col_size")}</th>
                      <th className="px-3 py-2 text-right text-muted-foreground font-normal">{t("col_entry")}</th>
                      <th className="px-3 py-2 text-right text-muted-foreground font-normal">{t("col_now")}</th>
                      <th className="px-3 py-2 text-right text-muted-foreground font-normal">{t("col_pnl")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positionsList.length === 0 && (
                      <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">{t("no_open_positions")}</td></tr>
                    )}
                    {positionsList.map((p) => (
                      <tr key={p.id} className="border-b border-border/50 hover:bg-secondary/40 transition-colors">
                        <td className="px-4 py-2 text-foreground max-w-[200px] truncate">{p.market_question}</td>
                        <td className={cn("px-3 py-2 text-right font-bold", p.side === "YES" ? "text-[hsl(var(--success))]" : "text-destructive")}>{p.side}</td>
                        <td className="px-3 py-2 text-right tabular-nums">${p.size_usd.toFixed(0)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{(p.entry_price * 100).toFixed(1)}¢</td>
                        <td className="px-3 py-2 text-right tabular-nums">{(p.current_price * 100).toFixed(1)}¢</td>
                        <td className={cn("px-3 py-2 text-right tabular-nums font-bold", p.unrealized_pnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>
                          {p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">{t("risk_summary")}</div>
          {risk ? (
            <div className="space-y-3">
              {[
                { label: t("risk_deployed"), value: `${(risk.deployed_pct * 100).toFixed(1)}%`, sub: `$${risk.deployed_capital_usd.toFixed(0)} / $${risk.total_capital_usd.toFixed(0)}` },
                { label: t("risk_daily_remaining"), value: `$${risk.daily_loss_remaining_usd.toFixed(0)}`, warn: risk.daily_loss_remaining_usd < 50 },
                { label: t("risk_largest_position"), value: `${((risk.largest_position_pct ?? 0) * 100).toFixed(1)}%` },
                { label: t("risk_var"), value: `$${(risk.var_95 ?? 0).toFixed(2)}` },
                { label: t("risk_correlation"), value: `${((risk.correlation_risk_score ?? 0) * 100).toFixed(0)}%`, warn: (risk.correlation_risk_score ?? 0) > 0.7 },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="block text-[11px] text-muted-foreground">{item.label}</span>
                    {item.sub && <span className="block text-[10px] text-muted-foreground/80 font-mono mt-0.5">{item.sub}</span>}
                  </div>
                  <span className={cn("text-xs font-mono font-bold tabular-nums", item.warn ? "text-[hsl(var(--warning))]" : "text-foreground")}>{item.value}</span>
                </div>
              ))}
              <div className="pt-2 border-t border-border/60 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="block text-[11px] text-muted-foreground">{t("reconciliation_status")}</span>
                  <span className={cn(
                    "text-xs font-mono font-bold tabular-nums uppercase",
                    reconciliationIsOk ? "text-[hsl(var(--success))]" :
                    reconciliationStatus === "warning" ? "text-[hsl(var(--warning))]" :
                    reconciliationStatus === "critical" ? "text-destructive" : "text-muted-foreground"
                  )}>
                    {reconciliationStatus === "ok" ? t("reconciliation_ok") :
                     reconciliationStatus === "warning" ? t("reconciliation_warning") :
                     reconciliationStatus === "critical" ? t("reconciliation_critical") : t("reconciliation_unknown")}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="block text-[11px] text-muted-foreground">{t("reconciliation_delta")}</span>
                  <span className={cn(
                    "text-xs font-mono font-bold tabular-nums",
                    (reconciliationDeltaUsd ?? 0) >= 0 ? "text-[hsl(var(--success))]" : "text-destructive"
                  )}>
                    {(reconciliationDeltaUsd ?? 0) >= 0 ? "+" : ""}${(reconciliationDeltaUsd ?? 0).toFixed(2)}
                    <span className="text-[10px] text-muted-foreground ml-1">
                      ({((reconciliationDeltaPct ?? 0) * 100).toFixed(2)}%)
                    </span>
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="block text-[11px] text-muted-foreground">{t("reconciliation_updated")}</span>
                  <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
                    {reconciliationUpdatedAt ? new Date(reconciliationUpdatedAt).toLocaleString() : "—"}
                  </span>
                </div>
              </div>
              <div>
                <div className="h-1.5 bg-border rounded-full mt-2 overflow-hidden">
                  <div className={cn("h-full rounded-full transition-all",
                    risk.deployed_pct > 0.8 ? "bg-destructive" :
                    risk.deployed_pct > 0.6 ? "bg-[hsl(var(--warning))]" : "bg-primary"
                  )} style={{ width: `${Math.min(risk.deployed_pct * 100, 100)}%` }} />
                </div>
              </div>
            </div>
          ) : <Skeleton className="h-40" />}
        </div>
      </div>

      <div className="bg-card border border-border rounded-md">
        <div className="flex items-center px-4 py-2 border-b border-border">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("system_log")}</span>
        </div>
        <div className="font-mono text-[11px] max-h-52 overflow-y-auto p-3 space-y-0.5">
          {logsList.length === 0 && <span className="text-muted-foreground">{t("no_log_entries")}</span>}
          {logsList.map((log) => (
            <div key={log.id} className="flex flex-wrap gap-x-3 gap-y-1 hover:bg-secondary/30 px-1 py-1 rounded">
              <span className="text-muted-foreground shrink-0">
                {new Date(log.created_at).toLocaleTimeString("en-US", { hour12: false })}
              </span>
              <span className={cn("shrink-0 uppercase w-8",
                log.level === "error" ? "text-destructive" :
                log.level === "warning" ? "text-[hsl(var(--warning))]" : "text-primary")}>{log.level.slice(0, 4)}</span>
              <span className="text-muted-foreground shrink-0 w-20 truncate">[{log.module}]</span>
              <span className="text-foreground min-w-0 flex-1">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
