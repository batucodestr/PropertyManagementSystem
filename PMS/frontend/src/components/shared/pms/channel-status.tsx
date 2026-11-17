import { CHANNEL_STYLES } from "@/components/shared/pms/badges";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useTranslations } from "@/i18n";
import { CheckIcon, RegenerateIcon, XIcon } from "@/icons";
import { api, errorMessage } from "@/lib/api";
import type { ChannelListing } from "@/lib/pms/types";
import { cn } from "@/utils";
import { useState } from "react";

function ChannelPill({ label, on, channel }: { label: string; on: boolean; channel: "airbnb" | "booking" }) {
  const s = CHANNEL_STYLES[channel];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-xs font-medium",
        on ? cn(s.bg, s.text, s.border) : "border-gray-200 text-gray-400 dark:border-gray-700 dark:text-gray-500",
      )}
    >
      {on ? <CheckIcon className="size-3" /> : <XIcon className="size-3" />}
      {label}
    </span>
  );
}

/** "Airbnb ✓ / Booking ✗ / Senkron hatası" rozetleri. */
export function ChannelStatusBadges({ listing, className }: { listing: ChannelListing | null | undefined; className?: string }) {
  const t = useTranslations("pms.channelStatus");
  if (!listing) {
    return (
      <span className={cn("inline-flex rounded-lg border border-dashed border-gray-300 px-2 py-0.5 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400", className)}>
        {t("notLinked")}
      </span>
    );
  }
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
      <ChannelPill label={t("airbnb")} on={listing.airbnb_connected} channel="airbnb" />
      <ChannelPill label={t("booking")} on={listing.booking_connected} channel="booking" />
      {listing.sync_status === "error" && (
        <span title={listing.last_error} className="inline-flex rounded-lg border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {t("syncError")}
        </span>
      )}
      {listing.sync_status === "pending" && (
        <span className="inline-flex rounded-lg border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          {t("syncPending")}
        </span>
      )}
    </span>
  );
}

/** Evi Beds24'e elle senkronlar (POST /api/integrations/properties/{id}/sync/). */
export function SyncNowButton({
  propertyId,
  onDone,
  onError,
  size = "xs",
  className,
}: {
  propertyId: string;
  onDone?: (listing: ChannelListing) => void;
  onError?: (message: string) => void;
  size?: "xs" | "sm";
  className?: string;
}) {
  const t = useTranslations("pms.channelStatus");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const listing = await api.post<ChannelListing>(`/integrations/properties/${propertyId}/sync/`);
      onDone?.(listing);
    } catch (e) {
      onError?.(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button variant="outline" size={size} className={className} disabled={busy} onClick={run}>
      {busy ? <Spinner /> : <RegenerateIcon className="size-4" />}
      {busy ? t("syncing") : t("syncNow")}
    </Button>
  );
}
