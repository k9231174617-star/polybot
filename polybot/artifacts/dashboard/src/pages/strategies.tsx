import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetPaperStats,
  getGetPaperStatsQueryKey,
  useGetSignals,
  getGetSignalsQueryKey,
  useGetPaperPositions,
  getGetPaperPositionsQueryKey,
  useGetBotConfig,
  getGetBotConfigQueryKey,
  useUpdateBotConfig,
} from "@workspace/api-client-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/lib/i18n";
import { Layers3, ShieldCheck, Sparkles } from "lucide-react";

const SIGNAL_LABELS: Record<string, string> = {
  price_discrepancy: "Price Discrepancy",
  cross_market_arb: "Cross-Market Arb",
  momentum: "Momentum",
  sentiment_lag: "Sentiment Lag",
  implied_prob: "Implied Probability",
  roda_oracle_lag: "RODA",
  lch_cascade: "LCH Cascade",
};

const SIGNAL_COLORS: Record<string, string> = {
  price_discrepancy: "hsl(var(--primary))",
  cross_market_arb: "hsl(142 71% 45%)",
  momentum: "hsl(var(--warning))",
  sentiment_lag: "hsl(280 70% 60%)",
  implied_prob: "hsl(200 70% 55%)",
  roda_oracle_lag: "hsl(30 90% 55%)",
  lch_cascade: "hsl(0 72% 60%)",
};

function formatStrategy(type: string): string {
  return SIGNAL_LABELS[type] ?? type.replace(/_/g, " ");
}

function StatCard({ label, value, sub, positive }: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  return (
    <div className="bg-card border border-border rounded-md p-4 space-y-1">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn(
        "text-xl font-mono font-bold tabular-nums",
        positive === true ? "text-success" : positive === false ? "text-destructive" : "text-foreground"
      )}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function Strategies() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const updateConfig = useUpdateBotConfig();
  const { data: botConfig, isLoading: configLoading } = useGetBotConfig({
    query: { queryKey: getGetBotConfigQueryKey() }
  });
  const { data: paperStats, isLoading: paperLoading } = useGetPaperStats({ query: { queryKey: getGetPaperStatsQueryKey() } });
  const { data: signals = [], isLoading: signalsLoading } = useGetSignals({ status: "all", limit: 200 }, {
    query: { queryKey: getGetSignalsQueryKey({ status: "all", limit: 200 }) }
  });
  const { data: paperPositions = [], isLoading: positionsLoading } = useGetPaperPositions({ status: "all" }, {
    query: { queryKey: getGetPaperPositionsQueryKey({ status: "all" }) }
  });

  const rows = useMemo(() => {
    const paperByType = paperStats?.by_signal_type ?? {};
    const signalAgg: Record<string, { total: number; pending: number; avgEdge: number; avgConf: number }> = {};
    for (const signal of signals) {
      const key = String(signal.signal_type ?? "unknown");
      const bucket = signalAgg[key] ?? { total: 0, pending: 0, avgEdge: 0, avgConf: 0 };
      bucket.total += 1;
      if (signal.status === "pending") bucket.pending += 1;
      bucket.avgEdge += Number(signal.edge ?? 0);
      bucket.avgConf += Number(signal.confidence ?? 0);
      signalAgg[key] = bucket;
    }

    const openAgg: Record<string, { count: number; exposure: number }> = {};
    for (const position of paperPositions) {
      if (position.status !== "open") continue;
      const key = String(position.signal_type ?? "unknown");
      const bucket = openAgg[key] ?? { count: 0, exposure: 0 };
      bucket.count += 1;
      bucket.exposure += Number(position.size_usd ?? 0);
      openAgg[key] = bucket;
    }

    const types = new Set([
      ...Object.keys(paperByType),
      ...Object.keys(signalAgg),
      ...Object.keys(openAgg),
    ]);

    return Array.from(types).map((type) => {
      const paper = paperByType[type] ?? { total: 0, wins: 0, pnl: 0, win_rate: 0 };
      const signalsForType = signalAgg[type] ?? { total: 0, pending: 0, avgEdge: 0, avgConf: 0 };
      const open = openAgg[type] ?? { count: 0, exposure: 0 };
      const totalSignals = signalsForType.total || 0;
      return {
        type,
        label: formatStrategy(type),
        pnl: Number(paper.pnl ?? 0),
        totalTrades: Number(paper.total ?? 0),
        wins: Number(paper.wins ?? 0),
        winRate: Number(paper.win_rate ?? 0),
        pendingSignals: signalsForType.pending,
        liveSignals: signalsForType.total,
        openPositions: open.count,
        exposureUsd: open.exposure,
        avgEdge: totalSignals > 0 ? signalsForType.avgEdge / totalSignals : 0,
        avgConf: totalSignals > 0 ? signalsForType.avgConf / totalSignals : 0,
      };
    }).sort((a, b) => b.pnl - a.pnl || b.liveSignals - a.liveSignals);
  }, [paperStats, signals, paperPositions]);

  const totalPnl = rows.reduce((sum, row) => sum + row.pnl, 0);
  const bestStrategy = rows[0];
  const bestWinRate = [...rows].sort((a, b) => b.winRate - a.winRate)[0];
  const activeSignals = rows.reduce((sum, row) => sum + row.pendingSignals, 0);
  const openExposure = rows.reduce((sum, row) => sum + row.exposureUsd, 0);
  const chartData = rows.map((row) => ({
    name: row.type,
    label: row.label,
    pnl: row.pnl,
    color: SIGNAL_COLORS[row.type] ?? "hsl(var(--primary))",
  }));

  const recentSignals = [...signals]
    .sort((a, b) => new Date(String(b.detected_at)).getTime() - new Date(String(a.detected_at)).getTime())
    .slice(0, 20);

  const strategyControls = [
    {
      key: "roda_enabled" as const,
      name: t("strategy_roda"),
      description: t("strategy_roda_desc"),
      enabled: botConfig?.roda_enabled ?? true,
    },
    {
      key: "lch_enabled" as const,
      name: t("strategy_lch"),
      description: t("strategy_lch_desc"),
      enabled: botConfig?.lch_enabled ?? true,
    },
  ];

  const onToggleStrategy = (key: "roda_enabled" | "lch_enabled", enabled: boolean) => {
    updateConfig.mutate(
      { data: { [key]: enabled } },
      {
        onSuccess: async () => {
          await queryClient.invalidateQueries({ queryKey: getGetBotConfigQueryKey() });
        },
      },
    );
  };

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Layers3 className="w-4 h-4 text-primary" />
            <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("strategies_title")}</h1>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">{t("strategies_subtitle")}</p>
          <p className="mt-1 text-[10px] text-muted-foreground">{t("strategies_note")}</p>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded border border-primary/20 bg-primary/10 text-primary w-fit">
          {rows.length} {t("active")}
        </span>
      </div>

      <div className="bg-card border border-border rounded-md p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t("strategy_controls")}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {configLoading ? Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          )) : strategyControls.map((strategy) => (
            <div key={strategy.key} className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
              <div className="min-w-0">
                <div className="text-sm text-foreground">{strategy.name}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">{strategy.description}</div>
                <div className={cn(
                  "mt-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
                  strategy.enabled
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-muted-foreground/20 bg-muted/40 text-muted-foreground",
                )}>
                  {strategy.enabled ? t("enabled") : t("disabled")}
                </div>
              </div>
              <Switch
                checked={strategy.enabled}
                onCheckedChange={(checked) => onToggleStrategy(strategy.key, checked)}
                disabled={updateConfig.isPending}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {paperLoading || signalsLoading || positionsLoading ? Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        )) : <>
          <StatCard label={t("strategy_total_pnl")} value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`} positive={totalPnl >= 0} />
          <StatCard label={t("best_strategy")} value={bestStrategy ? bestStrategy.label : "—"} sub={bestStrategy ? `$${bestStrategy.pnl.toFixed(2)} · ${bestStrategy.totalTrades} trades` : undefined} positive={bestStrategy ? bestStrategy.pnl >= 0 : undefined} />
          <StatCard label={t("strategy_pending_signals")} value={String(activeSignals)} sub={t("strategy_live_queue")} />
          <StatCard label={t("strategy_open_exposure")} value={`$${openExposure.toFixed(2)}`} sub={bestWinRate ? `${t("strategy_best_wr")} ${bestWinRate.label}: ${(bestWinRate.winRate * 100).toFixed(1)}%` : undefined} positive={openExposure === 0 ? undefined : openExposure >= 0} />
        </>}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-card border border-border rounded-md p-4 space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("strategy_pnl_chart")}</div>
            <div className="text-[10px] text-muted-foreground">{t("strategy_source_note")}</div>
          </div>
          {rows.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">{t("no_strategies")}</div>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} interval={0} />
                  <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", fontSize: 11 }} formatter={(v: number) => [`$${v.toFixed(2)}`, t("strategy_total_pnl")]}/>
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-md p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("strategy_leaderboard")}</div>
          </div>
          {rows.length === 0 ? (
            <div className="text-xs text-muted-foreground">{t("no_strategies")}</div>
          ) : (
            <div className="space-y-2">
              {rows.slice(0, 5).map((row, idx) => (
                <div key={row.type} className="border border-border rounded-md p-3 space-y-2">
                  <div className="flex items-center gap-2 justify-between">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">#{idx + 1}</div>
                      <div className="text-sm text-foreground truncate">{row.label}</div>
                    </div>
                    <div className={cn("text-sm font-mono font-bold tabular-nums", row.pnl >= 0 ? "text-success" : "text-destructive")}>
                      {row.pnl >= 0 ? "+" : ""}${row.pnl.toFixed(2)}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-muted-foreground">
                    <div>{t("strategy_win_rate")}: <span className={cn("text-foreground", row.winRate >= 0.5 ? "text-success" : "text-destructive")}>{(row.winRate * 100).toFixed(1)}%</span></div>
                    <div className="text-right">{t("strategy_trades")}: <span className="text-foreground tabular-nums">{row.totalTrades}</span></div>
                    <div>{t("strategy_open_positions")}: <span className="text-foreground tabular-nums">{row.openPositions}</span></div>
                    <div className="text-right">{t("strategy_pending_signals")}: <span className="text-foreground tabular-nums">{row.pendingSignals}</span></div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-muted-foreground">
                    <div>{t("strategy_avg_edge")}: <span className={cn("text-foreground tabular-nums", row.avgEdge >= 0 ? "text-success" : "text-destructive")}>{row.avgEdge >= 0 ? "+" : ""}{(row.avgEdge * 100).toFixed(2)}%</span></div>
                    <div className="text-right">{t("strategy_avg_confidence")}: <span className="text-foreground tabular-nums">{(row.avgConf * 100).toFixed(0)}%</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("strategy_status")}</div>
          <div className="text-[10px] text-muted-foreground">{recentSignals.length} {t("recent_signals")}</div>
        </div>
        <div className="md:hidden divide-y divide-border/50">
          {recentSignals.length === 0 ? (
            <div className="px-4 py-10 text-center text-xs text-muted-foreground">{t("no_signals")}</div>
          ) : recentSignals.map((signal) => (
            <div key={signal.id} className="px-4 py-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm text-foreground">{signal.market_question}</div>
                  <div className="mt-1 flex flex-wrap gap-2 items-center">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{formatStrategy(String(signal.signal_type))}</span>
                    <span className={cn("text-[10px] font-bold", signal.direction === "YES" ? "text-success" : "text-destructive")}>{signal.direction}</span>
                    <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border", signal.status === "pending" ? "bg-[hsl(var(--warning))]/10 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/20" : signal.status === "acted" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-border text-muted-foreground border-border")}>{String(signal.status).toUpperCase()}</span>
                  </div>
                </div>
                <div className={cn("text-[10px] font-mono font-bold", signal.edge >= 0 ? "text-success" : "text-destructive")}>{signal.edge >= 0 ? "+" : ""}{(signal.edge * 100).toFixed(2)}%</div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
                <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_mkt")}</div><div className="text-foreground tabular-nums">{(signal.market_price * 100).toFixed(1)}¢</div></div>
                <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_model")}</div><div className="text-foreground tabular-nums">{(signal.model_probability * 100).toFixed(1)}%</div></div>
                <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_conf")}</div><div className="text-foreground tabular-nums">{(signal.confidence * 100).toFixed(0)}%</div></div>
              </div>
            </div>
          ))}
        </div>

        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-border bg-secondary/30">
                <th className="px-4 py-3 text-left text-muted-foreground font-normal">{t("col_market")}</th>
                <th className="px-3 py-3 text-left text-muted-foreground font-normal">{t("col_type")}</th>
                <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_dir")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_mkt")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_model")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_edge")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_conf")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_status")}</th>
                <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_detected")}</th>
              </tr>
            </thead>
            <tbody>
              {recentSignals.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-16 text-center text-muted-foreground">{t("no_signals")}</td></tr>
              ) : recentSignals.map((signal) => (
                <tr key={signal.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                  <td className="px-4 py-2.5 max-w-[280px] truncate text-foreground">{signal.market_question}</td>
                  <td className="px-3 py-2.5"><span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{formatStrategy(String(signal.signal_type))}</span></td>
                  <td className={cn("px-3 py-2.5 text-center font-bold", signal.direction === "YES" ? "text-success" : "text-destructive")}>{signal.direction}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{(signal.market_price * 100).toFixed(1)}¢</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{(signal.model_probability * 100).toFixed(1)}%</td>
                  <td className={cn("px-3 py-2.5 text-right font-bold tabular-nums", signal.edge >= 0 ? "text-success" : "text-destructive")}>{signal.edge >= 0 ? "+" : ""}{(signal.edge * 100).toFixed(2)}%</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{(signal.confidence * 100).toFixed(0)}%</td>
                  <td className="px-3 py-2.5 text-right"><span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border", signal.status === "pending" ? "bg-[hsl(var(--warning))]/10 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/20" : signal.status === "acted" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-border text-muted-foreground border-border")}>{String(signal.status).toUpperCase()}</span></td>
                  <td className="px-3 py-2.5 text-right text-[10px] text-muted-foreground">{new Date(String(signal.detected_at)).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
