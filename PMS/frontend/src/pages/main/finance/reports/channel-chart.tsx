import { useTheme } from "@/contexts";
import { useTranslations } from "@/i18n";
import { formatCurrency } from "@/lib/pms/format";
import type { FinanceSummary } from "@/lib/pms/types";
import type { ApexOptions } from "apexcharts";
import ReactApexChart from "react-apexcharts";

// scripts/validate_palette.js ile doğrulandı (açık: #fcfcfb, koyu: #1a1a19 yüzeyde tüm kontroller PASS).
const PALETTE = {
  light: { net: "#465fff", commission: "#dc6803", surface: "#ffffff" },
  dark: { net: "#5c73ff", commission: "#dc6803", surface: "#111827" },
};

/** Kanal karşılaştırması: her kanal için net + komisyon yığılmış yatay çubuk (toplam ≈ brüt). */
export function ChannelChart({ data }: { data: FinanceSummary["by_channel"] }) {
  const t = useTranslations("pms.finance.reports");
  const tch = useTranslations("pms.finance.channels");
  const { theme } = useTheme();
  const dark = theme === "dark";
  const colors = PALETTE[dark ? "dark" : "light"];
  const muted = dark ? "#94a3b8" : "#667085";

  const options: ApexOptions = {
    colors: [colors.net, colors.commission],
    chart: { type: "bar", stacked: true, toolbar: { show: false }, fontFamily: "Outfit, sans-serif", background: "transparent" },
    plotOptions: { bar: { horizontal: true, barHeight: "48%", borderRadius: 4, borderRadiusApplication: "end", borderRadiusWhenStacked: "last" } },
    // Yığılmış segmentler arasında 2px yüzey boşluğu
    stroke: { show: true, width: 2, colors: [colors.surface] },
    dataLabels: { enabled: false },
    grid: { borderColor: dark ? "#1f2937" : "#eef0f3", strokeDashArray: 3, xaxis: { lines: { show: true } }, yaxis: { lines: { show: false } } },
    xaxis: {
      categories: data.map((c) => tch(c.source)),
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { formatter: (v) => formatCurrency(Number(v)), style: { colors: muted, fontSize: "11px" } },
    },
    yaxis: { labels: { style: { colors: muted, fontSize: "13px" } } },
    legend: { position: "top", horizontalAlign: "left", labels: { colors: muted }, markers: { size: 6 } },
    tooltip: {
      theme: dark ? "dark" : "light",
      shared: true,
      intersect: false,
      y: { formatter: (v) => formatCurrency(v ?? 0) },
    },
  };

  const series = [
    { name: t("net"), data: data.map((c) => Number(c.net)) },
    { name: t("commission"), data: data.map((c) => Number(c.commission)) },
  ];

  return <ReactApexChart key={theme} options={options} series={series} type="bar" height={260} />;
}
