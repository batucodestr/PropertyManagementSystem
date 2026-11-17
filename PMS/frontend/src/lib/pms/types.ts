// Backend (Django REST) cevaplarının şekli. Alan adları API ile birebir aynıdır (snake_case).
// ID'ler UUID string'dir. DRF, Decimal alanları string olarak gönderir ("120.00").

export type ReservationStatus =
  | "pending"
  | "confirmed"
  | "cancelled"
  | "completed"
  | "no_show";
export type ReservationSource = "direct" | "airbnb" | "booking" | "other";
export type TaskStatus = "pending" | "in_progress" | "completed";
export type HousekeepingStatus = "ready" | "dirty" | "cleaning";
export type HousekeepingPriority = "normal" | "urgent";
export type TaskType = "general" | "maintenance" | "inspection";
export type TaskPriority = "low" | "normal" | "high" | "critical";

export interface TaskPhoto {
  id: string;
  general_task: string | null;
  housekeeping_task: string | null;
  image: string;
  caption: string;
  created_at: string;
}

export interface UserSummary {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  groups: string[];
  role: "cleaner" | "manager";
}

export interface PropertyImage {
  id: number;
  property: string;
  image: string;
  alt_text: string;
}

export interface Property {
  id: string;
  name: string;
  description: string;
  phone: string;
  email: string;
  address: string;
  city: string;
  country: string;
  postal_code: string;
  max_guests: number;
  bedroom_count: number;
  bed_count: number;
  bathroom_count: number;
  area: string;
  base_price: string;
  is_active: boolean;
  default_cleaner: number | null;
  housekeeping_status: HousekeepingStatus;
  images: PropertyImage[];
  created_at: string;
  updated_at: string;
}

export interface Guest {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  nationality: string;
  notes: string | null;
  identity_number_masked: string; // identity_number sadece yazılır, okunmaz
  created_at: string;
  updated_at: string;
}

export interface Reservation {
  id: string;
  property: string; // property id
  guest: string; // guest id
  check_in: string; // yyyy-MM-dd
  check_out: string;
  adults: number;
  children: number;
  total_price: string;
  currency: string;
  status: ReservationStatus;
  source: ReservationSource;
  special_requests: string;
  external_source_id: string; // Beds24 booking id ("" = yerel)
  channel_booking_ref: string; // Airbnb / Booking.com onay kodu
  last_synced_at: string | null;
  channel_commission: string | null;
  commission_is_estimated: boolean;
  cleaning_fee: string;
  taxes: string;
  net_amount: string;
  payout_status: PayoutStatus;
  payout_date: string | null;
  created_at: string;
  updated_at: string;
}

export type PayoutStatus = "pending" | "paid";

export interface StayRecord {
  id: string;
  reservation: string;
  actual_check_in: string | null;
  actual_check_out: string | null;
  notes: string;
}

export interface HousekeepingTask {
  id: string;
  property: string;
  reservation: string | null;
  assigned_to: number | null;
  status: TaskStatus;
  scheduled_date: string;
  completed_date: string | null;
  notes: string;
  cost: string | null;
  priority: HousekeepingPriority;
  is_auto: boolean;
  started_at: string | null;
  property_name: string;
  assigned_to_name: string | null;
  photos: TaskPhoto[];
  created_at: string;
  updated_at: string;
}

export interface GeneralTask {
  id: string;
  property: string;
  description: string;
  assigned_to: number | null;
  due_date: string;
  completed_date: string | null;
  status: TaskStatus;
  cost: string | null;
  task_type: TaskType;
  priority: TaskPriority;
  calendar_closed_until: string | null;
  property_name: string;
  photos: TaskPhoto[];
  created_at: string;
  updated_at: string;
}

// ---- Kanal yöneticisi (Beds24) ----
export type SyncStatus = "ok" | "pending" | "error";

export interface ChannelListing {
  id: string;
  provider: string;
  property: string;
  external_listing_id: string;
  external_room_id: string;
  external_url: string;
  sync_enabled: boolean;
  sync_status: SyncStatus;
  last_synced_at: string | null;
  last_error: string;
  airbnb_markup_percent: string;
  booking_markup_percent: string;
  airbnb_connected: boolean;
  booking_connected: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChannelOverviewRow {
  property: { id: string; name: string; city: string; is_active: boolean };
  listing: ChannelListing | null;
}

export interface ChannelOverview {
  provider: string;
  configured: boolean;
  webhook_configured: boolean;
  webhook_auto_register: boolean;
  last_poll_at: string | null;
  photos_supported: boolean;
  channel_status_manual: boolean;
  commissions: Record<"airbnb" | "booking", string>;
  suggested_markup: Record<"airbnb" | "booking", string>;
  results: ChannelOverviewRow[];
}

export interface SyncLog {
  id: string;
  connection: string;
  action: string;
  status: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ---- Fiyat ve müsaitlik ----
export type RateSource = "daily" | "seasonal" | "weekend" | "base";
export type DayReason = "" | "closed" | "block" | "reservation" | "inactive";

export interface DayRate {
  date: string;
  price: string;
  min_stay: number;
  closed: boolean;
  available: boolean;
  source: RateSource;
  reason: DayReason;
}

export interface RatesResponse {
  property: string;
  base_price: string;
  from: string;
  to: string;
  days: DayRate[];
}

export interface SeasonalRate {
  id: string;
  property: string;
  name: string;
  start_date: string;
  end_date: string;
  nightly_price: string;
  weekend_price: string | null;
  min_stay: number | null;
  created_at: string;
  updated_at: string;
}

// ---- Finans ----
export type TransactionType = "income" | "expense";
export type ExpenseCategory =
  | "cleaning" | "maintenance" | "electricity" | "water" | "internet" | "gas"
  | "dues" | "supplies" | "tax" | "other";
export type TransactionCategory = ExpenseCategory | "reservation" | "other_income";

export interface FinancialTransaction {
  id: string;
  property: string;
  property_name: string;
  reservation: string | null;
  transaction_type: TransactionType;
  category: TransactionCategory;
  category_label: string;
  amount: string;
  currency: string;
  description: string;
  transaction_date: string;
  receipt: string | null;
  is_automatic: boolean;
  housekeeping_task: string | null;
  general_task: string | null;
  recurring_expense: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecurringExpense {
  id: string;
  property: string;
  property_name: string;
  category: ExpenseCategory;
  category_label: string;
  amount: string;
  currency: string;
  description: string;
  day_of_month: number;
  start_date: string;
  end_date: string | null;
  is_active: boolean;
}

export interface Payment {
  id: string;
  property: string;
  property_name: string;
  guest: string;
  guest_name: string;
  source: ReservationSource;
  status: ReservationStatus;
  check_in: string;
  check_out: string;
  currency: string;
  channel_booking_ref: string;
  external_source_id: string;
  total_price: string;
  channel_commission: string | null;
  commission_is_estimated: boolean;
  cleaning_fee: string;
  taxes: string;
  net_amount: string;
  payout_status: PayoutStatus;
  payout_date: string | null;
}

export interface FinanceFigures {
  gross: string;
  commission: string;
  taxes: string;
  net: string;
  expenses: string;
  other_income: string;
  profit: string;
  nights: number;
  reservations: number;
  adr: string;
  available_nights?: number;
  occupancy?: string;
  revpar?: string;
}

export interface FinanceSummary {
  from: string;
  to: string;
  property: string | null;
  totals: FinanceFigures & { available_nights: number; occupancy: string; revpar: string };
  expenses_by_category: Record<string, string>;
  by_property: (FinanceFigures & { property: string; name: string })[];
  by_channel: (FinanceFigures & { source: ReservationSource })[];
  by_month: { month: string; gross: string; commission: string; net: string; expenses: string; profit: string; nights: number }[];
}

// ---- Operasyon / mesajlaşma ----
export interface CleanerTask {
  id: string;
  property: string;
  property_name: string;
  property_address: string;
  scheduled_date: string;
  priority: HousekeepingPriority;
  status: TaskStatus;
  started_at: string | null;
  completed_date: string | null;
  notes: string;
  next_check_in: { check_in: string; guests: number } | null;
  photos: TaskPhoto[];
}

export interface AccessInfo {
  wifi_name: string;
  wifi_password: string;
  door_code: string;
  check_in_instructions: string;
  house_rules: string;
  updated_at?: string;
}

export type MessageTrigger =
  | "booking_confirmed" | "before_check_in" | "check_in_day" | "check_out_morning" | "after_check_out";

export interface MessageTemplate {
  id: string;
  name: string;
  trigger: MessageTrigger;
  offset_hours: number;
  send_time: string | null;
  language: string;
  subject: string;
  body: string;
  is_active: boolean;
}

export type ScheduledStatus = "pending" | "sending" | "sent" | "failed" | "cancelled" | "skipped";

export interface ScheduledMessage {
  id: string;
  reservation: string;
  template: string;
  template_name: string;
  trigger: MessageTrigger;
  send_at: string;
  status: ScheduledStatus;
  channel: string;
  sent_at: string | null;
  attempts: number;
  error: string;
}

export interface Conversation {
  id: string;
  reservation: string;
  channel: string;
  source: ReservationSource;
  guest_name: string;
  property_name: string;
  check_in: string;
  check_out: string;
  reservation_status: ReservationStatus;
  last_message_at: string | null;
  last_message_preview: string;
  unread_count: number;
}

export interface InboxMessage {
  id: string;
  direction: "in" | "out";
  source: "guest" | "host" | "system" | "auto";
  body: string;
  sent_at: string;
  status: "received" | "sent" | "failed";
  is_read: boolean;
  error: string;
  sent_by_name: string | null;
}
