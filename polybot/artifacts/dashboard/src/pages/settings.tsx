import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  useGetBotConfig, getGetBotConfigQueryKey,
  useUpdateBotConfig,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { useI18n } from "@/lib/i18n";

const configSchema = z.object({
  edge_threshold: z.number().min(0.01).max(0.5),
  max_position_pct: z.number().min(0.01).max(0.5),
  daily_loss_limit_pct: z.number().min(0.01).max(0.5),
  kelly_fraction: z.number().min(0.05).max(1.0),
  scan_interval_seconds: z.number().int().min(5).max(300),
  use_limit_orders: z.boolean(),
  min_liquidity_usd: z.number().min(100),
  max_correlated_exposure_pct: z.number().min(0.05).max(1.0),
  paper_trading: z.boolean(),
  paper_capital_usd: z.number().min(100).max(1_000_000),
});

type ConfigFormValues = z.infer<typeof configSchema>;

export default function Settings() {
  const { t } = useI18n();
  const { data: config, isLoading } = useGetBotConfig({
    query: { queryKey: getGetBotConfigQueryKey() }
  });
  const updateConfig = useUpdateBotConfig();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const form = useForm<ConfigFormValues>({
    resolver: zodResolver(configSchema),
    defaultValues: {
      edge_threshold: 0.05,
      max_position_pct: 0.05,
      daily_loss_limit_pct: 0.03,
      kelly_fraction: 0.25,
      scan_interval_seconds: 30,
      use_limit_orders: true,
      min_liquidity_usd: 1000,
      max_correlated_exposure_pct: 0.15,
      paper_trading: true,
      paper_capital_usd: 1000,
    },
  });

  useEffect(() => {
    if (config) {
      form.reset({
        edge_threshold: config.edge_threshold,
        max_position_pct: config.max_position_pct,
        daily_loss_limit_pct: config.daily_loss_limit_pct,
        kelly_fraction: config.kelly_fraction,
        scan_interval_seconds: config.scan_interval_seconds,
        use_limit_orders: config.use_limit_orders,
        min_liquidity_usd: config.min_liquidity_usd,
        max_correlated_exposure_pct: config.max_correlated_exposure_pct,
        paper_trading: config.paper_trading,
        paper_capital_usd: config.paper_capital_usd,
      });
    }
  }, [config, form]);

  function onSubmit(values: ConfigFormValues) {
    updateConfig.mutate({ data: values }, {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetBotConfigQueryKey() });
        toast({ title: t("config_saved"), description: t("config_saved_desc") });
      },
      onError: () => {
        toast({ title: t("config_error"), description: t("config_error_desc"), variant: "destructive" });
      }
    });
  }

  if (isLoading) return <Skeleton className="h-96 w-full" />;

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t("settings_title")}</h1>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          {/* Signal Detection */}
          <div className="bg-card border border-border rounded-md p-5 space-y-5">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("signal_detection")}</div>

            <FormField control={form.control} name="edge_threshold" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("edge_threshold")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">{(field.value * 100).toFixed(1)}%</span>
                </div>
                <FormControl>
                  <Slider min={1} max={30} step={0.5} value={[field.value * 100]}
                    onValueChange={([v]) => field.onChange(v / 100)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("edge_threshold_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />

            <FormField control={form.control} name="kelly_fraction" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("kelly_fraction")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">{(field.value * 100).toFixed(0)}%</span>
                </div>
                <FormControl>
                  <Slider min={5} max={100} step={5} value={[field.value * 100]}
                    onValueChange={([v]) => field.onChange(v / 100)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("kelly_fraction_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />

            <FormField control={form.control} name="scan_interval_seconds" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("scan_interval")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">{field.value}s</span>
                </div>
                <FormControl>
                  <Slider min={5} max={300} step={5} value={[field.value]}
                    onValueChange={([v]) => field.onChange(v)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("scan_interval_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />
          </div>

          {/* Risk Limits */}
          <div className="bg-card border border-border rounded-md p-5 space-y-5">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("risk_limits_section")}</div>

            <FormField control={form.control} name="max_position_pct" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("max_position")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">{(field.value * 100).toFixed(1)}%</span>
                </div>
                <FormControl>
                  <Slider min={1} max={25} step={0.5} value={[field.value * 100]}
                    onValueChange={([v]) => field.onChange(v / 100)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("max_position_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />

            <FormField control={form.control} name="daily_loss_limit_pct" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("daily_loss_limit_setting")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-[hsl(var(--warning))]">{(field.value * 100).toFixed(1)}%</span>
                </div>
                <FormControl>
                  <Slider min={1} max={20} step={0.5} value={[field.value * 100]}
                    onValueChange={([v]) => field.onChange(v / 100)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("daily_loss_limit_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />

            <FormField control={form.control} name="max_correlated_exposure_pct" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("max_correlated")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">{(field.value * 100).toFixed(0)}%</span>
                </div>
                <FormControl>
                  <Slider min={5} max={50} step={5} value={[field.value * 100]}
                    onValueChange={([v]) => field.onChange(v / 100)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("max_correlated_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />

            <FormField control={form.control} name="min_liquidity_usd" render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs text-muted-foreground">{t("min_liquidity")}</FormLabel>
                <FormControl>
                  <Input type="number" {...field} onChange={(e) => field.onChange(Number(e.target.value))}
                    className="bg-background border-border font-mono h-8 text-xs" />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("min_liquidity_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />
          </div>

          {/* Execution */}
          <div className="bg-card border border-border rounded-md p-5 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("execution_section")}</div>

            <FormField control={form.control} name="use_limit_orders" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <div>
                    <FormLabel className="text-xs text-foreground">{t("use_limit_orders")}</FormLabel>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{t("use_limit_orders_desc")}</div>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </div>
              </FormItem>
            )} />
          </div>

          {/* Paper Trading */}
          <div className="bg-card border border-border rounded-md p-5 space-y-5">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("paper_trading_section")}
            </div>

            <FormField control={form.control} name="paper_trading" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <div>
                    <FormLabel className="text-xs text-foreground">{t("paper_trading_toggle")}</FormLabel>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{t("paper_trading_toggle_desc")}</div>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </div>
              </FormItem>
            )} />

            <FormField control={form.control} name="paper_capital_usd" render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel className="text-xs text-muted-foreground">{t("paper_capital_setting")}</FormLabel>
                  <span className="text-xs font-mono font-bold text-primary">${field.value.toLocaleString()}</span>
                </div>
                <FormControl>
                  <Slider min={100} max={100000} step={100} value={[field.value]}
                    onValueChange={([v]) => field.onChange(v)} />
                </FormControl>
                <div className="text-[10px] text-muted-foreground">{t("paper_capital_desc")}</div>
                <FormMessage />
              </FormItem>
            )} />
          </div>

          <Button type="submit" disabled={updateConfig.isPending} className="w-full font-mono">
            {updateConfig.isPending ? t("saving") : t("save_config")}
          </Button>
        </form>
      </Form>
    </div>
  );
}
