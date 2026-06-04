import { useState } from "react";
import {
  useGetPaperStats,
  useGetPaperPositions,
  useGetPaperTrades,
  useGetPaperChart,
  useGetBotConfig,
  getGetPaperStatsQueryKey,
  getGetPaperPositionsQueryKey,
  getGetPaperTradesQueryKey,
  getGetPaperChartQueryKey,
  getGetBotConfigQueryKey,
} from "@workspace/api-client-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { FlaskConical } from "lucide-react";

const SIGNAL_COLORS: Record<string, string> = {
  price_discrepancy: "hsl(var(--primary))",
  momentum: "hsl(var(--warning))",
  cross_market_arb: "hsl(142 71% 45%)",
  sentiment_lag: "hsl(280 70% 60%)",
  implied_prob: "hsl(200 70% 55%)",
  roda_oracle_lag: "hsl(30 90% 55%)",
  lch_cascade: "hsl(0 72% 60%)",
  hybrid_roda_lch_cross: "hsl(260 75% 58%)",
};

const SIGNAL_LABELS: Record<string, string> = {
  price_discrepancy: "Price Discrepancy",
  momentum: "Momentum",
  cross_market_arb: "Cross-Market Arb",
  sentiment_lag: "Sentiment Lag",
  implied_prob: "Implied Probability",
  roda_oracle_lag: "RODA",
  lch_cascade: "LCH Cascade",
  hybrid_roda_lch_cross: "Hybrid",
};

function StatCard({ label, value, sub, positive }: {
  label: string; value: string; sub?: string; positive?: boolean;
}) {
  return (
    <div className="bg-card border border-border rounded-md p-4 space-y-1">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn(
        "text-xl font-mono font-bold",
        positive === true ? "text-success" : positive === false ? "text-destructive" : "text-foreground"
      )}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function Paper() {
  const { t } = useI18n();
  const [period, setPeriod] = useState<"1d" | "7d" | "30d" | "all">("7d");

  const { data: config } = useGetBotConfig({ query: { queryKey: getGetBotConfigQueryKey() } });
  const { data: stats } = useGetPaperStats({ query: { queryKey: getGetPaperStatsQueryKey() } });
  const { data: positions = [] } = useGetPaperPositions(
    { status: "open" },
    { query: { queryKey: getGetPaperPositionsQueryKey({ status: "open" }) } }
  );
  const { data: trades = [] } = useGetPaperTrades(
    { limit: 50 },
    { query: { queryKey: getGetPaperTradesQueryKey({ limit: 50 }) } }
  );
  const { data: chart = [] } = useGetPaperChart(
    { period },
    { query: { queryKey: getGetPaperChartQueryKey({ period }) } }
  );

  const paperOn = config?.paper_trading ?? true;
  const pnlPositive = (stats?.cumulative_pnl ?? 0) >= 0;
  const returnPositive = (stats?.total_return_pct ?? 0) >= 0;

  const chartData = chart.map((p) => ({
    time: new Date(p.timestamp).toLocaleDateString(),
    pnl: Number(p.cumulative_pnl.toFixed(2)),
    value: Number(p.portfolio_value.toFixed(2)),
  }));

  const byType = stats?.by_signal_type ?? {};

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <FlaskConical className="w-5 h-5 text-primary" />
        <div className="min-w-0">
          <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("paper_title")}</h1>
          <p className="text-[10px] text-muted-foreground">{t("paper_subtitle")}</p>
        </div>
        <span className={cn(
          "sm:ml-auto text-[10px] font-mono px-2 py-0.5 rounded border w-fit",
          paperOn ? "border-primary text-primary bg-primary/10" : "border-muted text-muted-foreground"
        )}>{paperOn ? t("paper_badge_on") : t("paper_badge_off")}</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label={t("paper_capital")} value={`$${(stats?.capital_usd ?? 0).toLocaleString()}`} />
        <StatCard label={t("paper_portfolio")} value={`$${(stats?.portfolio_value ?? 0).toFixed(2)}`} />
        <StatCard label={t("paper_cum_pnl")} value={`${pnlPositive ? "+" : ""}$${(stats?.cumulative_pnl ?? 0).toFixed(2)}`} positive={pnlPositive} />
        <StatCard label={t("paper_return")} value={`${returnPositive ? "+" : ""}${(stats?.total_return_pct ?? 0).toFixed(2)}%`} positive={returnPositive} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label={t("paper_trades")} value={String(stats?.total_trades ?? 0)} />
        <StatCard label={t("paper_open")} value={String(stats?.open_positions ?? 0)} />
        <StatCard label={t("paper_wins")} value={String(stats?.wins ?? 0)} positive={(stats?.wins ?? 0) > 0 ? true : undefined} />
        <StatCard label={t("paper_losses")} value={String(stats?.losses ?? 0)} positive={(stats?.losses ?? 0) === 0 ? true : (stats?.losses ?? 0) > 0 ? false : undefined} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label={t("paper_win_rate")} value={`${((stats?.win_rate ?? 0) * 100).toFixed(1)}%`} positive={(stats?.win_rate ?? 0) >= 0.5} />
        <StatCard label={t("paper_avg_pnl")} value={`$${(stats?.avg_pnl_per_trade ?? 0).toFixed(2)}`} positive={(stats?.avg_pnl_per_trade ?? 0) >= 0} />
        <StatCard label={t("paper_best")} value={`$${(stats?.best_trade ?? 0).toFixed(2)}`} positive />
        <StatCard label={t("paper_worst")} value={`$${(stats?.worst_trade ?? 0).toFixed(2)}`} positive={(stats?.worst_trade ?? 0) >= 0} />
      </div>

      <div className="bg-card border border-border rounded-md p-4 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("paper_equity_curve")}</div>
          <div className="flex flex-wrap gap-1">
            {(["1d", "7d", "30d", "all"] as const).map((p) => (
              <button key={p} onClick={() => setPeriod(p)} className={cn(
                "px-2 py-0.5 text-[10px] font-mono rounded border transition-colors",
                period === p ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:text-foreground"
              )}>{p}</button>
            ))}
          </div>
        </div>
        <div className="h-52">
          {chartData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground text-xs">{t("no_paper_trades")}</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="paperGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="time" tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${v}`} />
                <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", fontSize: 11 }} formatter={(v: number) => [`$${v.toFixed(2)}`, ""]} />
                <Area type="monotone" dataKey="pnl" stroke="hsl(var(--primary))" fill="url(#paperGrad)" strokeWidth={2} dot={false} name="P&L" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {Object.keys(byType).length > 0 && (
        <div className="bg-card border border-border rounded-md p-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("paper_by_type")}</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.entries(byType).map(([type, data]) => (
                <div key={type} className="border border-border rounded-md p-3 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: SIGNAL_COLORS[type] ?? "hsl(var(--muted))" }} />
                    <span className="text-xs font-mono font-medium text-foreground">{SIGNAL_LABELS[type] ?? type.replace(/_/g, " ")}</span>
                  </div>
                <div className="grid grid-cols-3 gap-1 text-[10px] text-muted-foreground">
                  <div>Trades: <span className="text-foreground font-mono">{data.total}</span></div>
                  <div>WR: <span className={cn("font-mono", (data.win_rate ?? 0) >= 0.5 ? "text-success" : "text-destructive")}>{((data.win_rate ?? 0) * 100).toFixed(0)}%</span></div>
                  <div>P&L: <span className={cn("font-mono", (data.pnl ?? 0) >= 0 ? "text-success" : "text-destructive")}>{(data.pnl ?? 0) >= 0 ? "+" : ""}${(data.pnl ?? 0).toFixed(2)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="px-4 py-3 border-b border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("paper_positions")} ({positions.length})</div>
        {positions.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-muted-foreground">{t("no_paper_positions")}</div>
        ) : (
          <>
            <div className="md:hidden divide-y divide-border/50">
              {positions.map((p) => (
                <div key={p.id} className="px-4 py-3 space-y-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-foreground" title={p.market_question}>{p.market_question}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">{p.signal_type.replace(/_/g, " ")}</div>
                    </div>
                    <span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded shrink-0", p.side === "YES" ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive")}>{p.side}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_size")}</div><div className="text-foreground tabular-nums">${p.size_usd.toFixed(2)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_entry")}</div><div className="text-foreground tabular-nums">{p.entry_price.toFixed(3)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_now")}</div><div className="text-foreground tabular-nums">{p.current_price.toFixed(3)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_pnl")}</div><div className={cn("tabular-nums", p.unrealized_pnl >= 0 ? "text-success" : "text-destructive")}>{p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}</div></div>
                  </div>
                  <div className="text-[10px] font-mono text-muted-foreground">{p.unrealized_pnl_pct >= 0 ? "+" : ""}{p.unrealized_pnl_pct.toFixed(1)}%</div>
                </div>
              ))}
            </div>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="px-4 py-2 text-left font-normal">{t("col_market")}</th>
                    <th className="px-3 py-2 text-left font-normal">{t("col_side")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_size")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_entry")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_now")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_pnl")}</th>
                    <th className="px-3 py-2 text-left font-normal">{t("paper_signal_type")}</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id} className="border-b border-border/50 hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-2 max-w-[180px] truncate font-medium" title={p.market_question}>{p.market_question}</td>
                      <td className="px-3 py-2"><span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded", p.side === "YES" ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive")}>{p.side}</span></td>
                      <td className="px-3 py-2 text-right font-mono">${p.size_usd.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-mono">{p.entry_price.toFixed(3)}</td>
                      <td className="px-3 py-2 text-right font-mono">{p.current_price.toFixed(3)}</td>
                      <td className={cn("px-3 py-2 text-right font-mono", p.unrealized_pnl >= 0 ? "text-success" : "text-destructive")}>{p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}<span className="text-muted-foreground ml-1">({p.unrealized_pnl_pct.toFixed(1)}%)</span></td>
                      <td className="px-3 py-2 text-[10px] text-muted-foreground font-mono">{p.signal_type.replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="px-4 py-3 border-b border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("paper_history")} ({trades.length})</div>
        {trades.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-muted-foreground">{t("no_paper_trades")}</div>
        ) : (
          <>
            <div className="md:hidden divide-y divide-border/50">
              {trades.map((tr) => (
                <div key={tr.id} className="px-4 py-3 space-y-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-foreground" title={tr.market_question}>{tr.market_question}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">{tr.signal_type.replace(/_/g, " ")}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded uppercase", tr.action === "buy" ? "bg-primary/20 text-primary" : "bg-secondary text-muted-foreground")}>{tr.action}</span>
                      <span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded", tr.side === "YES" ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive")}>{tr.side}</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_size")}</div><div className="text-foreground tabular-nums">${tr.size_usd.toFixed(2)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_price")}</div><div className="text-foreground tabular-nums">{tr.price.toFixed(3)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_pnl")}</div><div className={cn("tabular-nums font-bold", tr.realized_pnl == null ? "text-muted-foreground" : tr.realized_pnl >= 0 ? "text-success" : "text-destructive")}>{tr.realized_pnl == null ? "—" : `${tr.realized_pnl >= 0 ? "+" : ""}$${tr.realized_pnl.toFixed(2)}`}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_time")}</div><div className="text-foreground text-[10px] tabular-nums">{new Date(tr.executed_at).toLocaleString()}</div></div>
                  </div>
                </div>
              ))}
            </div>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="px-4 py-2 text-left font-normal">{t("col_market")}</th>
                    <th className="px-3 py-2 text-left font-normal">{t("col_action")}</th>
                    <th className="px-3 py-2 text-left font-normal">{t("col_side")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_size")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_price")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_pnl")}</th>
                    <th className="px-3 py-2 text-left font-normal">{t("paper_signal_type")}</th>
                    <th className="px-3 py-2 text-right font-normal">{t("col_time")}</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((tr) => (
                    <tr key={tr.id} className="border-b border-border/50 hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-2 max-w-[160px] truncate font-medium" title={tr.market_question}>{tr.market_question}</td>
                      <td className="px-3 py-2"><span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded uppercase", tr.action === "buy" ? "bg-primary/20 text-primary" : "bg-secondary text-muted-foreground")}>{tr.action}</span></td>
                      <td className="px-3 py-2"><span className={cn("font-mono text-[10px] px-1.5 py-0.5 rounded", tr.side === "YES" ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive")}>{tr.side}</span></td>
                      <td className="px-3 py-2 text-right font-mono">${tr.size_usd.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-mono">{tr.price.toFixed(3)}</td>
                      <td className={cn("px-3 py-2 text-right font-mono", tr.realized_pnl == null ? "text-muted-foreground" : tr.realized_pnl >= 0 ? "text-success" : "text-destructive")}>{tr.realized_pnl == null ? "—" : `${tr.realized_pnl >= 0 ? "+" : ""}$${tr.realized_pnl.toFixed(2)}`}</td>
                      <td className="px-3 py-2 text-[10px] text-muted-foreground font-mono">{tr.signal_type.replace(/_/g, " ")}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap">{new Date(tr.executed_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
