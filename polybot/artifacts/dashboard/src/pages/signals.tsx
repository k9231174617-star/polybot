import { useState } from "react";
import { useGetSignals, getGetSignalsQueryKey } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";

type StatusFilter = "pending" | "acted" | "dismissed" | "all";

const SIGNAL_LABELS: Record<string, string> = {
  price_discrepancy: "Price Discrepancy",
  cross_market_arb: "Cross-Market Arb",
  momentum: "Momentum",
  sentiment_lag: "Sentiment Lag",
  implied_prob: "Implied Probability",
};

export default function Signals() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const { t } = useI18n();

  const { data: signals, isLoading } = useGetSignals({ status: statusFilter, limit: 100 }, {
    query: { queryKey: getGetSignalsQueryKey({ status: statusFilter, limit: 100 }) }
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("signals_title")}</h1>
        <div className="flex flex-wrap gap-1 lg:ml-auto">
          {(["pending", "acted", "dismissed", "all"] as StatusFilter[]).map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={cn("text-[10px] sm:text-xs font-mono px-3 py-1 rounded border transition-colors",
                statusFilter === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"
              )}>
              {s.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <>
          <div className="md:hidden space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md p-3 space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-28" />
                <div className="grid grid-cols-2 gap-2">
                  <Skeleton className="h-10 rounded-md" />
                  <Skeleton className="h-10 rounded-md" />
                  <Skeleton className="h-10 rounded-md" />
                  <Skeleton className="h-10 rounded-md" />
                </div>
              </div>
            ))}
          </div>
          <div className="hidden md:block bg-card border border-border rounded-md overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border bg-secondary/30">
                  <th className="px-4 py-3 text-left text-muted-foreground font-normal">{t("col_market")}</th>
                  <th className="px-3 py-3 text-left text-muted-foreground font-normal">{t("col_type")}</th>
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_dir")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_mkt")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_model")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_kelly")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_conf")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_status")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_detected")}</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/40">
                    {Array.from({ length: 10 }).map((__, j) => (
                      <td key={j} className="px-3 py-2.5"><Skeleton className="h-3 w-full" /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="md:hidden space-y-2">
            {(signals ?? []).length === 0 && (
              <div className="bg-card border border-border rounded-md px-4 py-12 text-center text-muted-foreground text-xs">{t("no_signals")}</div>
            )}
            {(signals ?? []).map((s) => (
              <div key={s.id} className="bg-card border border-border rounded-md p-3 space-y-3">
                <div>
                  <div className="text-sm text-foreground leading-snug">{s.market_question}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{SIGNAL_LABELS[s.signal_type] ?? s.signal_type}</span>
                    <span className={cn("text-[10px] font-bold", s.direction === "YES" ? "text-[hsl(var(--success))]" : "text-destructive")}>{s.direction}</span>
                    <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border",
                      s.status === "pending" ? "bg-[hsl(var(--warning))]/10 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/20" :
                      s.status === "acted" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" :
                      "bg-border text-muted-foreground border-border"
                    )}>{s.status.toUpperCase()}</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_mkt")}</div><div className="text-foreground tabular-nums">{(s.market_price * 100).toFixed(1)}¢</div></div>
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_model")}</div><div className="text-foreground tabular-nums">{(s.model_probability * 100).toFixed(1)}%</div></div>
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_edge")}</div><div className={cn("tabular-nums font-bold", s.edge > 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{s.edge > 0 ? "+" : ""}{(s.edge * 100).toFixed(2)}%</div></div>
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_kelly")}</div><div className="text-foreground tabular-nums">${s.kelly_size_usd.toFixed(0)}</div></div>
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_conf")}</div><div className="text-foreground tabular-nums">{(s.confidence * 100).toFixed(0)}%</div></div>
                  <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_detected")}</div><div className="text-foreground text-[10px] tabular-nums">{new Date(s.detected_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</div></div>
                </div>
              </div>
            ))}
          </div>

          <div className="hidden md:block bg-card border border-border rounded-md overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border bg-secondary/30">
                  <th className="px-4 py-3 text-left text-muted-foreground font-normal">{t("col_market")}</th>
                  <th className="px-3 py-3 text-left text-muted-foreground font-normal">{t("col_type")}</th>
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_dir")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_mkt")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_model")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_kelly")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_conf")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_status")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_detected")}</th>
                </tr>
              </thead>
              <tbody>
                {!isLoading && (signals ?? []).length === 0 && (
                  <tr><td colSpan={10} className="px-4 py-16 text-center text-muted-foreground">{t("no_signals")}</td></tr>
                )}
                {(signals ?? []).map((s) => (
                  <tr key={s.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                    <td className="px-4 py-2.5 max-w-xs"><div className="truncate text-foreground">{s.market_question}</div></td>
                    <td className="px-3 py-2.5"><span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{SIGNAL_LABELS[s.signal_type] ?? s.signal_type}</span></td>
                    <td className="px-3 py-2.5 text-center"><span className={cn("font-bold", s.direction === "YES" ? "text-[hsl(var(--success))]" : "text-destructive")}>{s.direction}</span></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{(s.market_price * 100).toFixed(1)}¢</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{(s.model_probability * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2.5 text-right"><span className={cn("font-bold tabular-nums", s.edge > 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{s.edge > 0 ? "+" : ""}{(s.edge * 100).toFixed(2)}%</span></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">${s.kelly_size_usd.toFixed(0)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{(s.confidence * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2.5 text-right"><span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border", s.status === "pending" ? "bg-[hsl(var(--warning))]/10 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/20" : s.status === "acted" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-border text-muted-foreground border-border")}>{s.status.toUpperCase()}</span></td>
                    <td className="px-3 py-2.5 text-right text-[10px] text-muted-foreground">{new Date(s.detected_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
