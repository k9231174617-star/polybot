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
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("positions_title")}</h1>
        <div className="flex gap-4 ml-auto font-mono text-xs">
          <div className="text-muted-foreground">{t("total_size")}: <span className="text-foreground tabular-nums">${totalSize.toFixed(2)}</span></div>
          <div className="text-muted-foreground">{t("unrealized_pnl")}:
            <span className={cn("tabular-nums ml-1", totalUnrealizedPnl >= 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>
              {totalUnrealizedPnl >= 0 ? "+" : ""}${totalUnrealizedPnl.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
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
            {isLoading && Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b border-border/40">
                {Array.from({ length: 9 }).map((__, j) => (
                  <td key={j} className="px-3 py-2.5"><Skeleton className="h-3 w-full" /></td>
                ))}
              </tr>
            ))}
            {!isLoading && open.length === 0 && (
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
                    <span className={cn("px-2 py-0.5 rounded-sm text-[10px] font-bold border",
                      p.side === "YES"
                        ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border-[hsl(var(--success))]/20"
                        : "bg-destructive/10 text-destructive border-destructive/20"
                    )}>{p.side}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">${p.size_usd.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{(p.entry_price * 100).toFixed(1)}¢</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{(p.current_price * 100).toFixed(1)}¢</td>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums font-bold",
                    pnlPositive ? "text-[hsl(var(--success))]" : "text-destructive")}>
                    {pnlPositive ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
                    <div className={cn("text-[10px] font-normal", pnlPositive ? "text-[hsl(var(--success))]/70" : "text-destructive/70")}>
                      {pnlPositive ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}%
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                    +{((p.entry_edge ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {p.current_edge !== null && p.current_edge !== undefined ? (
                      <span className={cn(p.current_edge > 0 ? "text-[hsl(var(--success))]" : "text-destructive")}>
                        {p.current_edge > 0 ? "+" : ""}{(p.current_edge * 100).toFixed(1)}%
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right text-[10px] text-muted-foreground">
                    {new Date(p.opened_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
