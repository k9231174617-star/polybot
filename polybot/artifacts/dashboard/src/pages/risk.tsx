import { useGetRiskMetrics, getGetRiskMetricsQueryKey, useGetPnlSummary, getGetPnlSummaryQueryKey } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { RadialBarChart, RadialBar, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { useI18n } from "@/lib/i18n";

function MetricRow({ label, value, sub, warn = false, danger = false }: {
  label: string; value: string; sub?: string; warn?: boolean; danger?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="text-right">
        <div className={cn("text-sm font-mono font-bold tabular-nums",
          danger ? "text-destructive" : warn ? "text-[hsl(var(--warning))]" : "text-foreground")}>
          {value}
        </div>
        {sub && <div className="text-[10px] font-mono text-muted-foreground">{sub}</div>}
      </div>
    </div>
  );
}

export default function Risk() {
  const { t } = useI18n();
  const { data: risk, isLoading: riskLoading } = useGetRiskMetrics({
    query: { queryKey: getGetRiskMetricsQueryKey() }
  });
  const { data: pnl, isLoading: pnlLoading } = useGetPnlSummary({
    query: { queryKey: getGetPnlSummaryQueryKey() }
  });

  const deployedPct = risk?.deployed_pct ?? 0;
  const dailyLossUsedPct = risk
    ? 1 - (risk.daily_loss_remaining_usd / risk.daily_loss_limit_usd)
    : 0;

  const gaugeData = [{ value: deployedPct * 100, fill: deployedPct > 0.8 ? "hsl(var(--destructive))" : deployedPct > 0.6 ? "hsl(var(--warning))" : "hsl(217,91%,60%)" }];

  const winLossData = pnl ? [
    { name: "Wins", value: pnl.winning_trades, fill: "hsl(var(--success))" },
    { name: "Losses", value: pnl.losing_trades, fill: "hsl(var(--destructive))" },
  ] : [];

  return (
    <div className="space-y-4">
      <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("risk_title")}</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Capital Exposure */}
        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">{t("capital_exposure")}</div>
          {riskLoading ? <Skeleton className="h-40" /> : (
            <>
              <div className="flex items-center justify-center mb-4">
                <ResponsiveContainer width={160} height={100}>
                  <RadialBarChart cx="50%" cy="85%" innerRadius="60%" outerRadius="90%" startAngle={180} endAngle={0} data={gaugeData}>
                    <RadialBar background dataKey="value" cornerRadius={4} />
                  </RadialBarChart>
                </ResponsiveContainer>
              </div>
              <div className="text-center mb-4">
                <div className={cn("text-3xl font-mono font-bold tabular-nums",
                  deployedPct > 0.8 ? "text-destructive" : deployedPct > 0.6 ? "text-[hsl(var(--warning))]" : "text-primary")}>
                  {(deployedPct * 100).toFixed(1)}%
                </div>
                <div className="text-xs text-muted-foreground">{t("deployed_capital")}</div>
              </div>
              <MetricRow label={t("total_capital")} value={`$${(risk?.total_capital_usd ?? 0).toLocaleString()}`} />
              <MetricRow label={t("deployed")} value={`$${(risk?.deployed_capital_usd ?? 0).toFixed(2)}`} />
              <MetricRow label={t("free_capital")} value={`$${((risk?.total_capital_usd ?? 0) - (risk?.deployed_capital_usd ?? 0)).toFixed(2)}`} />
            </>
          )}
        </div>

        {/* Risk Limits */}
        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">{t("risk_limits")}</div>
          {riskLoading ? <Skeleton className="h-40" /> : (
            <>
              <MetricRow label={t("daily_loss_limit")} value={`$${(risk?.daily_loss_limit_usd ?? 0).toFixed(2)}`} />
              <MetricRow label={t("daily_loss_remaining")}
                value={`$${(risk?.daily_loss_remaining_usd ?? 0).toFixed(2)}`}
                warn={dailyLossUsedPct > 0.7} danger={dailyLossUsedPct > 0.9} />
              <div className="my-2">
                <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                  <span>{t("daily_loss_used")}</span>
                  <span>{(dailyLossUsedPct * 100).toFixed(0)}%</span>
                </div>
                <div className="h-1.5 bg-border rounded-full overflow-hidden">
                  <div className={cn("h-full rounded-full transition-all",
                    dailyLossUsedPct > 0.9 ? "bg-destructive" : dailyLossUsedPct > 0.7 ? "bg-[hsl(var(--warning))]" : "bg-primary"
                  )} style={{ width: `${Math.min(dailyLossUsedPct * 100, 100)}%` }} />
                </div>
              </div>
              <MetricRow label={t("max_single_position")} value={`$${(risk?.max_single_position_usd ?? 0).toFixed(2)}`} />
              <MetricRow label={t("largest_position")} value={`${((risk?.largest_position_pct ?? 0) * 100).toFixed(1)}%`}
                warn={(risk?.largest_position_pct ?? 0) > 0.07} />
              <MetricRow label={t("open_positions_count")} value={String(risk?.num_open_positions ?? 0)} />
            </>
          )}
        </div>

        {/* Trade Statistics */}
        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">{t("trade_statistics")}</div>
          {pnlLoading ? <Skeleton className="h-40" /> : (
            <>
              {winLossData.length > 0 && (
                <div className="flex items-center justify-center mb-3">
                  <ResponsiveContainer width={120} height={120}>
                    <PieChart>
                      <Pie data={winLossData} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value" strokeWidth={0}>
                        {winLossData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="ml-2 space-y-1">
                    <div className="flex items-center gap-2 text-xs">
                      <div className="w-2 h-2 rounded-full bg-[hsl(var(--success))]" />
                      <span className="text-muted-foreground">Wins: </span>
                      <span className="font-mono text-[hsl(var(--success))]">{pnl?.winning_trades ?? 0}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <div className="w-2 h-2 rounded-full bg-destructive" />
                      <span className="text-muted-foreground">Losses: </span>
                      <span className="font-mono text-destructive">{pnl?.losing_trades ?? 0}</span>
                    </div>
                  </div>
                </div>
              )}
              <MetricRow label={t("win_rate")} value={`${((pnl?.win_rate ?? 0) * 100).toFixed(1)}%`} />
              <MetricRow label={t("avg_edge")} value={`${((pnl?.avg_edge_captured ?? 0) * 100).toFixed(2)}%`} />
              <MetricRow label={t("best_trade")} value={`+$${(pnl?.best_trade_pnl ?? 0).toFixed(2)}`} />
              <MetricRow label={t("worst_trade")} value={`-$${Math.abs(pnl?.worst_trade_pnl ?? 0).toFixed(2)}`} warn />
              <MetricRow label={t("sharpe_ratio")} value={pnl?.sharpe_ratio != null ? pnl.sharpe_ratio.toFixed(2) : "—"} />
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">{t("var_title")}</div>
          {riskLoading ? <Skeleton className="h-20" /> : (
            <div className="space-y-1">
              <MetricRow label={t("var_95")} value={`$${(risk?.var_95 ?? 0).toFixed(2)}`}
                sub={t("var_desc")} warn={(risk?.var_95 ?? 0) > (risk?.total_capital_usd ?? 999999) * 0.05} />
              <MetricRow label={t("daily_pnl")} value={`${(risk?.daily_pnl ?? 0) >= 0 ? "+" : ""}$${(risk?.daily_pnl ?? 0).toFixed(2)}`}
                sub={`${((risk?.daily_pnl_pct ?? 0) * 100).toFixed(2)}% today`} />
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-md p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">{t("correlation_risk")}</div>
          {riskLoading ? <Skeleton className="h-20" /> : (
            <div className="space-y-3">
              <MetricRow label={t("corr_risk_score")}
                value={`${((risk?.correlation_risk_score ?? 0) * 100).toFixed(0)}%`}
                warn={(risk?.correlation_risk_score ?? 0) > 0.5}
                danger={(risk?.correlation_risk_score ?? 0) > 0.8} />
              <div>
                <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
                  <span>{t("low_correlation")}</span><span>{t("high_correlation")}</span>
                </div>
                <div className="h-2 bg-border rounded-full overflow-hidden">
                  <div className={cn("h-full rounded-full transition-all",
                    (risk?.correlation_risk_score ?? 0) > 0.8 ? "bg-destructive" :
                    (risk?.correlation_risk_score ?? 0) > 0.5 ? "bg-[hsl(var(--warning))]" : "bg-[hsl(var(--success))]"
                  )} style={{ width: `${((risk?.correlation_risk_score ?? 0) * 100)}%` }} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
