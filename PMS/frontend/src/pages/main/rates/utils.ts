import type { RateSource } from "@/lib/pms/types";

export const SOURCE_STYLES: Record<RateSource, string> = {
  base: "border-gray-200 bg-white dark:border-gray-800 dark:bg-white/3",
  seasonal: "border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10",
  weekend: "border-sky-200 bg-sky-50 dark:border-sky-500/30 dark:bg-sky-500/10",
  daily: "border-violet-200 bg-violet-50 dark:border-violet-500/30 dark:bg-violet-500/10",
};

export function inRange(day: string, from: string | null, to: string | null) {
  if (!from) return false;
  return day >= from && day <= (to ?? from);
}

// Varsayılan kanal komisyonları (%). Backend'deki DEFAULT_COMMISSIONS ile aynı.
export const COMMISSIONS = { airbnb: 15.5, booking: 15 } as const;

/** Komisyon sonrası aynı neti almak için gereken markup (%): 1 / (1 - c) - 1. */
export const suggestedMarkup = (commission: number) =>
  (Math.round((1 / (1 - commission / 100) - 1) * 10000) / 100).toFixed(2);

export const withMarkup = (base: number, percent: string) => base * (1 + (Number(percent) || 0) / 100);
