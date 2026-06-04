import { Link, useLocation } from "wouter";
import { useGetBotStatus, getGetBotStatusQueryKey, useControlBot } from "@workspace/api-client-react";
import { Play, Square, Pause, Activity, LineChart, Table2, Radar, ArrowLeftRight, ShieldAlert, Settings, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useI18n, type Lang } from "@/lib/i18n";

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: botStatus } = useGetBotStatus({ query: { queryKey: getGetBotStatusQueryKey() } });
  const controlBot = useControlBot();
  const { lang, setLang, t } = useI18n();

  const navItems = [
    { href: "/", label: t("nav_dashboard"), icon: Activity },
    { href: "/markets", label: t("nav_markets"), icon: Radar },
    { href: "/positions", label: t("nav_positions"), icon: Table2 },
    { href: "/signals", label: t("nav_signals"), icon: LineChart },
    { href: "/trades", label: t("nav_trades"), icon: ArrowLeftRight },
    { href: "/risk", label: t("nav_risk"), icon: ShieldAlert },
    { href: "/paper", label: t("nav_paper"), icon: FlaskConical },
    { href: "/settings", label: t("nav_settings"), icon: Settings },
  ];

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden selection:bg-primary/30">
      {/* Sidebar */}
      <div className="w-64 border-r border-border bg-card flex flex-col">
        {/* Header with logo + lang toggle */}
        <div className="h-16 flex items-center px-4 border-b border-border gap-2">
          <div className="flex items-center gap-2 text-primary font-mono font-bold tracking-tight flex-1 min-w-0">
            <div className="w-3 h-3 bg-primary rounded-sm animate-pulse shrink-0" />
            <span className="truncate">POLYBOT.TERM</span>
          </div>
          {/* Language Toggle */}
          <div className="flex shrink-0 rounded-md border border-border overflow-hidden text-[10px] font-mono">
            {(["en", "ru"] as Lang[]).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                data-testid={`lang-${l}`}
                className={cn(
                  "px-2 py-1 uppercase transition-colors",
                  lang === l
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                )}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-6 flex flex-col gap-1 px-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location === item.href;
            return (
              <Link key={item.href} href={item.href}>
                <div className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                )}>
                  <Icon className="w-4 h-4" />
                  {item.label}
                </div>
              </Link>
            );
          })}
        </div>

        {/* Bot Control Panel */}
        <div className="p-4 border-t border-border bg-card/50">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-medium text-muted-foreground">{t("system_status")}</span>
            <div className="flex items-center gap-2">
              <div className={cn("w-2 h-2 rounded-full", {
                "bg-success shadow-[0_0_8px_rgba(34,197,94,0.6)]": botStatus?.state === "running",
                "bg-warning shadow-[0_0_8px_rgba(245,158,11,0.6)]": botStatus?.state === "paused",
                "bg-muted-foreground": botStatus?.state === "stopped",
                "bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.6)]": botStatus?.state === "error",
              })} />
              <span className="text-xs font-mono uppercase text-foreground">{botStatus?.state || "UNKNOWN"}</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Button
              variant="outline"
              size="icon"
              className={cn("w-full h-8", botStatus?.state === "running" && "border-success text-success bg-success/10")}
              onClick={() => controlBot.mutate({ data: { action: "start" } })}
              disabled={botStatus?.state === "running"}
            >
              <Play className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className={cn("w-full h-8", botStatus?.state === "paused" && "border-warning text-warning bg-warning/10")}
              onClick={() => controlBot.mutate({ data: { action: "pause" } })}
              disabled={botStatus?.state !== "running"}
            >
              <Pause className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="w-full h-8 hover:border-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={() => controlBot.mutate({ data: { action: "stop" } })}
              disabled={botStatus?.state === "stopped" || !botStatus}
            >
              <Square className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <main className="flex-1 overflow-y-auto bg-background p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
