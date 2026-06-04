import { useGetTrades, getGetTradesQueryKey } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";

export default function Trades() {
  const { t } = useI18n();
  const { data: trades, isLoading } = useGetTrades({ limit: 200 }, {
    query: { queryKey: getGetTradesQueryKey({ limit: 200 }) }
  });

  const allTrades = trades ?? [];
  const totalRealizedPnl = allTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
  const totalFees = allTrades.reduce((sum, tr) => sum + (tr.fee_usd ?? 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("trades_title")}</h1>
        <div className="flex flex-wrap gap-3 sm:gap-4 sm:ml-auto font-mono text-xs">
          <div className="text-muted-foreground">{t("realized_pnl")}: <span className={cn("ml-1 tabular-nums", totalRealizedPnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{totalRealizedPnl >= 0 ? "+" : ""}${totalRealizedPnl.toFixed(2)}</span></div>
          <div className="text-muted-foreground">{t("total_fees")}: <span className="text-foreground tabular-nums">${totalFees.toFixed(2)}</span></div>
          <div className="text-muted-foreground">{t("trades_count")}: <span className="text-foreground tabular-nums">{allTrades.length}</span></div>
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
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_action")}</th>
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_side")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_size")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_price")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_slippage")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_fee")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("realized_pnl")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_type")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_time")}</th>
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
            {allTrades.length === 0 && (
              <div className="bg-card border border-border rounded-md px-4 py-12 text-center text-muted-foreground text-xs">{t("no_trades")}</div>
            )}
            {allTrades.map((tr) => {
              const pnl = tr.realized_pnl;
              return (
                <div key={tr.id} className="bg-card border border-border rounded-md p-3 space-y-3">
                  <div>
                    <div className="text-sm text-foreground leading-snug">{tr.market_question}</div>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border", tr.action === "buy" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-destructive/10 text-destructive border-destructive/20")}>{tr.action.toUpperCase()}</span>
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border", tr.side === "YES" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-destructive/10 text-destructive border-destructive/20")}>{tr.side}</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_size")}</div><div className="text-foreground tabular-nums">${tr.size_usd.toFixed(2)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_price")}</div><div className="text-foreground tabular-nums">{(tr.price * 100).toFixed(1)}¢</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_slippage")}</div><div className="text-foreground tabular-nums">{tr.slippage ? `${(tr.slippage * 100).toFixed(2)}%` : "—"}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_fee")}</div><div className="text-foreground tabular-nums">${(tr.fee_usd ?? 0).toFixed(3)}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("realized_pnl")}</div><div className={cn("tabular-nums font-bold", pnl == null ? "text-muted-foreground" : pnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{pnl == null ? "—" : `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`}</div></div>
                    <div className="rounded border border-border/70 px-2 py-1.5"><div className="text-muted-foreground">{t("col_time")}</div><div className="text-foreground text-[10px] tabular-nums">{new Date(tr.executed_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</div></div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="hidden md:block bg-card border border-border rounded-md overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border bg-secondary/30">
                  <th className="px-4 py-3 text-left text-muted-foreground font-normal">{t("col_market")}</th>
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_action")}</th>
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_side")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_size")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_price")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_slippage")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_fee")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("realized_pnl")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_type")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_time")}</th>
                </tr>
              </thead>
              <tbody>
                {allTrades.length === 0 && (
                  <tr><td colSpan={10} className="px-4 py-16 text-center text-muted-foreground">{t("no_trades")}</td></tr>
                )}
                {allTrades.map((tr) => {
                  const pnl = tr.realized_pnl;
                  return (
                    <tr key={tr.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-2.5 max-w-xs"><div className="truncate text-foreground">{tr.market_question}</div></td>
                      <td className="px-3 py-2.5 text-center"><span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border", tr.action === "buy" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-destructive/10 text-destructive border-destructive/20")}>{tr.action.toUpperCase()}</span></td>
                      <td className={cn("px-3 py-2.5 text-center font-bold", tr.side === "YES" ? "text-[hsl(var(--success))]" : "text-destructive")}>{tr.side}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">${tr.size_usd.toFixed(2)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{(tr.price * 100).toFixed(1)}¢</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">{tr.slippage ? `${(tr.slippage * 100).toFixed(2)}%` : "—"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">${(tr.fee_usd ?? 0).toFixed(3)}</td>
                      <td className="px-3 py-2.5 text-right">{pnl !== undefined && pnl !== null ? <span className={cn("tabular-nums font-bold", pnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}</span> : <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2.5 text-right text-muted-foreground"><span className="text-[10px] uppercase">{tr.order_type}</span></td>
                      <td className="px-3 py-2.5 text-right text-[10px] text-muted-foreground">{new Date(tr.executed_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
