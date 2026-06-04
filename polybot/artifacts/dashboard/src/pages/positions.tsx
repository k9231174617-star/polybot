import { useGetPositions, getGetPositionsQueryKey } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n";

export default function Positions() {
  const { t } = useI18n();
  const { data: positions, isLoading } = useGetPositions({
    query: { queryKey: getGetPositionsQueryKey() }
  });

  const open = (positions ?? []).filter((p) => p.status === "open");
  const totalUnrealizedPnl = open.reduce((sum, p) => sum + p.unrealized_pnl, 0);
  const totalSize = open.reduce((sum, p) => sum + p.size_usd, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("positions_title")}</h1>
        <div className="flex flex-wrap gap-3 sm:gap-4 sm:ml-auto font-mono text-xs">
          <div className="text-muted-foreground">{t("total_size")}: <span className="text-foreground tabular-nums">${totalSize.toFixed(2)}</span></div>
          <div className="text-muted-foreground">{t("unrealized_pnl")}: 
            <span className={cn("tabular-nums ml-1", totalUnrealizedPnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{
              totalUnrealizedPnl >= 0 ? "+" : ""
            }${totalUnrealizedPnl.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {isLoading ? (
        <>
          <div className="md:hidden space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md p-3 space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-24" />
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
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_side")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_size")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_entry")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_now")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_unreal_pnl")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_entry_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_cur_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_opened")}</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/40">
                    {Array.from({ length: 9 }).map((__, j) => (
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
            {open.length === 0 && (
              <div className="bg-card border border-border rounded-md px-4 py-12 text-center text-muted-foreground text-xs">{t("no_positions")}</div>
            )}
            {open.map((p) => {
              const pnlPositive = p.unrealized_pnl >= 0;
              return (
                <div key={p.id} className="bg-card border border-border rounded-md p-3 space-y-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-foreground">{p.market_question}</div>
                      <div className="text-[10px] text-muted-foreground">#{p.market_id.slice(0, 8)}</div>
                    </div>
                    <span className={cn("px-2 py-0.5 rounded-sm text-[10px] font-bold border shrink-0",
                      p.side === "YES"
                        ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20"
                        : "bg-destructive/10 text-destructive border-destructive/20"
                    )}>{p.side}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div className="rounded border border-border/70 px-2 py-1.5">
                      <div className="text-muted-foreground">{t("col_size")}</div>
                      <div className="text-foreground tabular-nums">${p.size_usd.toFixed(2)}</div>
                    </div>
                    <div className="rounded border border-border/70 px-2 py-1.5">
                      <div className="text-muted-foreground">{t("col_opened")}</div>
                      <div className="text-foreground tabular-nums">{new Date(p.opened_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</div>
                    </div>
                    <div className="rounded border border-border/70 px-2 py-1.5">
                      <div className="text-muted-foreground">{t("col_entry")}</div>
                      <div className="text-foreground tabular-nums">{(p.entry_price * 100).toFixed(1)}¢</div>
                    </div>
                    <div className="rounded border border-border/70 px-2 py-1.5">
                      <div className="text-muted-foreground">{t("col_now")}</div>
                      <div className="text-foreground tabular-nums">{(p.current_price * 100).toFixed(1)}¢</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                    <div>
                      <span className="text-muted-foreground">{t("col_unreal_pnl")}: </span>
                      <span className={cn("font-bold tabular-nums", pnlPositive ? "text-[hsl(var(--success))]" : "text-destructive")}>{pnlPositive ? "+" : ""}${p.unrealized_pnl.toFixed(2)}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-muted-foreground">{t("col_cur_edge")}: </span>
                      {p.current_edge !== null && p.current_edge !== undefined ? (
                        <span className={cn("font-bold tabular-nums", p.current_edge > 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{p.current_edge > 0 ? "+" : ""}{(p.current_edge * 100).toFixed(1)}%</span>
                      ) : <span className="text-muted-foreground">—</span>}
                    </div>
                    <div>
                      <span className="text-muted-foreground">{t("col_entry_edge")}: </span>
                      <span className="text-foreground tabular-nums">+{((p.entry_edge ?? 0) * 100).toFixed(1)}%</span>
                    </div>
                    <div className="text-right">
                      <span className={cn("text-[10px] font-normal", pnlPositive ? "text-[hsl(var(--success))]/70" : "text-destructive/70")}>{pnlPositive ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}%</span>
                    </div>
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
                  <th className="px-3 py-3 text-center text-muted-foreground font-normal">{t("col_side")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_size")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_entry")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_now")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_unreal_pnl")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_entry_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_cur_edge")}</th>
                  <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_opened")}</th>
                </tr>
              </thead>
              <tbody>
                {open.length === 0 && (
                  <tr><td colSpan={9} className="px-4 py-16 text-center text-muted-foreground">{t("no_positions")}</td></tr>
                )}
                {open.map((p) => {
                  const pnlPositive = p.unrealized_pnl >= 0;
                  return (
                    <tr key={p.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-2.5 max-w-xs">
                        <div className="truncate text-foreground">{p.market_question}</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">#{p.market_id.slice(0, 8)}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <span className={cn("px-2 py-0.5 rounded-sm text-[10px] font-bold border", p.side === "YES" ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20" : "bg-destructive/10 text-destructive border-destructive/20")}>{p.side}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">${p.size_usd.toFixed(2)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{(p.entry_price * 100).toFixed(1)}¢</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{(p.current_price * 100).toFixed(1)}¢</td>
                      <td className={cn("px-3 py-2.5 text-right tabular-nums font-bold", pnlPositive ? "text-[hsl(var(--success))]" : "text-destructive")}>
                        {pnlPositive ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
                        <div className={cn("text-[10px] font-normal", pnlPositive ? "text-[hsl(var(--success))]/70" : "text-destructive/70")}>{pnlPositive ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}%</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">+{((p.entry_edge ?? 0) * 100).toFixed(1)}%</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {p.current_edge !== null && p.current_edge !== undefined ? (
                          <span className={cn(p.current_edge > 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>{p.current_edge > 0 ? "+" : ""}{(p.current_edge * 100).toFixed(1)}%</span>
                        ) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[10px] text-muted-foreground">{new Date(p.opened_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</td>
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
