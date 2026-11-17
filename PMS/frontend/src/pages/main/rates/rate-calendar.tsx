import { useTranslations } from "@/i18n";
import { formatCurrency } from "@/lib/pms/format";
import type { DayRate } from "@/lib/pms/types";
import { cn } from "@/utils";
import { getISODay, parseISO } from "date-fns";
import { SOURCE_STYLES, inRange } from "./utils";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Aylık fiyat takvimi. Bir güne, sonra başka bir güne tıklamak aralık seçer. */
export function RateCalendar({
  days,
  selection,
  onSelect,
  today,
}: {
  days: DayRate[];
  selection: { from: string | null; to: string | null };
  onSelect: (day: string) => void;
  today: string;
}) {
  const t = useTranslations("pms.rates");
  if (days.length === 0) return null;
  const leading = getISODay(parseISO(days[0].date)) - 1;

  const statusLabel = (d: DayRate) =>
    d.reason === "reservation" ? t("booked")
      : d.reason === "closed" ? t("closed")
        : d.reason === "block" ? t("blocked")
          : d.reason === "inactive" ? t("inactive") : null;

  return (
    <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
      {WEEKDAYS.map((w) => (
        <div key={w} className="pb-1 text-center text-xs font-medium tracking-wide text-gray-500 uppercase dark:text-gray-400">
          {w}
        </div>
      ))}
      {Array.from({ length: leading }, (_, i) => <div key={`pad-${i}`} />)}
      {days.map((d) => {
        const selected = inRange(d.date, selection.from, selection.to);
        const past = d.date < today;
        const label = statusLabel(d);
        return (
          <button
            key={d.date}
            type="button"
            disabled={past}
            onClick={() => onSelect(d.date)}
            aria-pressed={selected}
            aria-label={`${d.date} ${formatCurrency(d.price)}${label ? ` ${label}` : ""}`}
            className={cn(
              "relative flex min-h-16 flex-col items-start rounded-lg border p-1.5 text-start transition-colors sm:min-h-20 sm:p-2",
              SOURCE_STYLES[d.source],
              !d.available && "bg-[repeating-linear-gradient(135deg,transparent,transparent_6px,rgba(148,163,184,0.15)_6px,rgba(148,163,184,0.15)_12px)]",
              past ? "cursor-not-allowed opacity-45" : "hover:border-brand-300 dark:hover:border-brand-500/50",
              selected && "ring-2 ring-brand-500 dark:ring-brand-400",
            )}
          >
            <span className={cn("text-xs font-medium text-gray-500 dark:text-gray-400", d.date === today && "text-brand-600 dark:text-brand-400")}>
              {Number(d.date.slice(8, 10))}
            </span>
            <span className="mt-auto text-xs font-semibold text-gray-900 sm:text-sm dark:text-white/90">
              {formatCurrency(d.price)}
            </span>
            <span className="hidden text-[11px] text-gray-500 sm:block dark:text-gray-400">
              {label ?? (d.min_stay > 1 ? t("minStay", { count: d.min_stay }) : " ")}
            </span>
            {label && (
              <span
                className={cn(
                  "absolute inset-e-1.5 top-1.5 size-2 rounded-full",
                  d.reason === "reservation" ? "bg-rose-500" : "bg-gray-500",
                )}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function RateLegend() {
  const t = useTranslations("pms.rates");
  const items: [string, string][] = [
    [t("legendBase"), SOURCE_STYLES.base],
    [t("legendSeasonal"), SOURCE_STYLES.seasonal],
    [t("legendWeekend"), SOURCE_STYLES.weekend],
    [t("legendDaily"), SOURCE_STYLES.daily],
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-600 dark:text-gray-400">
      {items.map(([label, cls]) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span className={cn("size-3 rounded border", cls)} /> {label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-rose-500" /> {t("legendBooked")}</span>
      <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-gray-500" /> {t("legendClosed")}</span>
    </div>
  );
}
