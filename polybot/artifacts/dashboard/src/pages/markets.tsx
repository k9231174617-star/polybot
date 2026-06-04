import { useState } from "react";
import { useGetMarkets, getGetMarketsQueryKey } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { useI18n } from "@/lib/i18n";

type StatusFilter = "active" | "resolved" | "all";

export default function Markets() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"edge" | "volume_24h" | "liquidity_usd">("edge");
  const { t } = useI18n();

  const { data: markets, isLoading } = useGetMarkets({ status: statusFilter, limit: 100 }, {
    query: { queryKey: getGetMarketsQueryKey({ status: statusFilter, limit: 100 }) }
  });

  const filtered = (markets ?? [])
    .filter((m) => !search || m.question.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === "edge") return ((b.edge ?? -999) - (a.edge ?? -999));
      if (sortBy === "volume_24h") return (b.volume_24h - a.volume_24h);
      return (b.liquidity_usd - a.liquidity_usd);
    });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("markets_title")}</h1>
        <div className="flex gap-1 ml-auto">
          {(["active", "resolved", "all"] as StatusFilter[]).map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={cn("text-xs font-mono px-3 py-1 rounded border transition-colors",
                statusFilter === s ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/20"
              )}>
              {s.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input placeholder={t("markets_search")} value={search} onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8 text-xs w-64 bg-card border-border" />
        </div>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-border bg-secondary/30">
              <th className="px-4 py-3 text-left text-muted-foreground font-normal">{t("col_market")}</th>
              <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_mkt_price")}</th>
              <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_model_prob")}</th>
              <th className="px-3 py-3 text-right cursor-pointer select-none" onClick={() => setSortBy("edge")}>
                <span className={cn(sortBy === "edge" ? "text-primary" : "text-muted-foreground font-normal")}>
                  {t("col_edge")} {sortBy === "edge" ? "▼" : ""}
                </span>
              </th>
              <th className="px-3 py-3 text-right cursor-pointer select-none" onClick={() => setSortBy("volume_24h")}>
                <span className={cn(sortBy === "volume_24h" ? "text-primary" : "text-muted-foreground font-normal")}>
                  {t("col_vol_24h")} {sortBy === "volume_24h" ? "▼" : ""}
                </span>
              </th>
              <th className="px-3 py-3 text-right cursor-pointer select-none" onClick={() => setSortBy("liquidity_usd")}>
                <span className={cn(sortBy === "liquidity_usd" ? "text-primary" : "text-muted-foreground font-normal")}>
                  {t("col_liquidity")} {sortBy === "liquidity_usd" ? "▼" : ""}
                </span>
              </th>
              <th className="px-3 py-3 text-right text-muted-foreground font-normal">{t("col_updated")}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 8 }).map((_, i) => (
              <tr key={i} className="border-b border-border/40">
                <td className="px-4 py-2.5"><Skeleton className="h-3 w-48" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-12 ml-auto" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-12 ml-auto" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-14 ml-auto" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-16 ml-auto" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-16 ml-auto" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-20 ml-auto" /></td>
              </tr>
            ))}
            {!isLoading && filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">{t("no_markets")}</td></tr>
            )}
            {filtered.map((m) => {
              const edge = m.edge ?? null;
              const hasEdge = edge !== null && Math.abs(edge) > 0.001;
              const positiveEdge = edge !== null && edge > 0;
              return (
                <tr key={m.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                  <td className="px-4 py-2.5 max-w-xs">
                    <div className="truncate text-foreground">{m.question}</div>
                    {m.category && <div className="text-[10px] text-muted-foreground mt-0.5">{m.category}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{(m.market_price * 100).toFixed(1)}¢</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                    {m.model_probability !== undefined && m.model_probability !== null
                      ? `${(m.model_probability * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {hasEdge ? (
                      <span className={cn(
                        "px-2 py-0.5 rounded-sm text-[10px] font-bold tabular-nums",
                        positiveEdge ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border border-[hsl(var(--success))]/20"
                          : "bg-destructive/10 text-destructive border border-destructive/20"
                      )}>
                        {positiveEdge ? "+" : ""}{(edge! * 100).toFixed(1)}%
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                    ${m.volume_24h >= 1000 ? `${(m.volume_24h / 1000).toFixed(0)}k` : m.volume_24h.toFixed(0)}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                    ${m.liquidity_usd >= 1000 ? `${(m.liquidity_usd / 1000).toFixed(0)}k` : m.liquidity_usd.toFixed(0)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground text-[10px]">
                    {new Date(m.last_updated).toLocaleTimeString("en-US", { hour12: false })}
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
