/**
 * ISO 3166-1 alpha-2 country catalog (a curated subset of ~80 high-traffic
 * markets — every country Stripe Connect supports plus key tourist
 * destinations). Each entry carries everything the UI needs:
 *
 *   • code      — ISO alpha-2 ("NZ", "IN", "AE")
 *   • name      — display name in English
 *   • flag      — single-codepoint regional-indicator emoji
 *   • timezone  — primary IANA tz used to auto-suggest event timezones
 *   • currency  — ISO 4217 used to auto-suggest the event currency
 *
 * Source of truth in one place so the create-event form, events listing,
 * and admin panels all stay in sync.
 */
export const COUNTRIES = [
  // Oceania
  { code: "NZ", name: "New Zealand",   flag: "🇳🇿", timezone: "Pacific/Auckland",  currency: "NZD" },
  { code: "AU", name: "Australia",     flag: "🇦🇺", timezone: "Australia/Sydney",  currency: "AUD" },
  { code: "FJ", name: "Fiji",          flag: "🇫🇯", timezone: "Pacific/Fiji",      currency: "FJD" },

  // North America
  { code: "US", name: "United States", flag: "🇺🇸", timezone: "America/New_York",  currency: "USD" },
  { code: "CA", name: "Canada",        flag: "🇨🇦", timezone: "America/Toronto",   currency: "CAD" },
  { code: "MX", name: "Mexico",        flag: "🇲🇽", timezone: "America/Mexico_City", currency: "MXN" },

  // South America
  { code: "BR", name: "Brazil",        flag: "🇧🇷", timezone: "America/Sao_Paulo", currency: "BRL" },
  { code: "AR", name: "Argentina",     flag: "🇦🇷", timezone: "America/Argentina/Buenos_Aires", currency: "ARS" },
  { code: "CL", name: "Chile",         flag: "🇨🇱", timezone: "America/Santiago",  currency: "CLP" },
  { code: "CO", name: "Colombia",      flag: "🇨🇴", timezone: "America/Bogota",    currency: "COP" },

  // Europe
  { code: "GB", name: "United Kingdom",flag: "🇬🇧", timezone: "Europe/London",     currency: "GBP" },
  { code: "IE", name: "Ireland",       flag: "🇮🇪", timezone: "Europe/Dublin",     currency: "EUR" },
  { code: "FR", name: "France",        flag: "🇫🇷", timezone: "Europe/Paris",      currency: "EUR" },
  { code: "DE", name: "Germany",       flag: "🇩🇪", timezone: "Europe/Berlin",     currency: "EUR" },
  { code: "ES", name: "Spain",         flag: "🇪🇸", timezone: "Europe/Madrid",     currency: "EUR" },
  { code: "IT", name: "Italy",         flag: "🇮🇹", timezone: "Europe/Rome",       currency: "EUR" },
  { code: "PT", name: "Portugal",      flag: "🇵🇹", timezone: "Europe/Lisbon",     currency: "EUR" },
  { code: "NL", name: "Netherlands",   flag: "🇳🇱", timezone: "Europe/Amsterdam",  currency: "EUR" },
  { code: "BE", name: "Belgium",       flag: "🇧🇪", timezone: "Europe/Brussels",   currency: "EUR" },
  { code: "AT", name: "Austria",       flag: "🇦🇹", timezone: "Europe/Vienna",     currency: "EUR" },
  { code: "CH", name: "Switzerland",   flag: "🇨🇭", timezone: "Europe/Zurich",     currency: "CHF" },
  { code: "PL", name: "Poland",        flag: "🇵🇱", timezone: "Europe/Warsaw",     currency: "PLN" },
  { code: "SE", name: "Sweden",        flag: "🇸🇪", timezone: "Europe/Stockholm",  currency: "SEK" },
  { code: "NO", name: "Norway",        flag: "🇳🇴", timezone: "Europe/Oslo",       currency: "NOK" },
  { code: "DK", name: "Denmark",       flag: "🇩🇰", timezone: "Europe/Copenhagen", currency: "DKK" },
  { code: "FI", name: "Finland",       flag: "🇫🇮", timezone: "Europe/Helsinki",   currency: "EUR" },
  { code: "CZ", name: "Czech Republic",flag: "🇨🇿", timezone: "Europe/Prague",     currency: "CZK" },
  { code: "GR", name: "Greece",        flag: "🇬🇷", timezone: "Europe/Athens",     currency: "EUR" },
  { code: "TR", name: "Türkiye",       flag: "🇹🇷", timezone: "Europe/Istanbul",   currency: "TRY" },

  // Middle East
  { code: "AE", name: "United Arab Emirates", flag: "🇦🇪", timezone: "Asia/Dubai", currency: "AED" },
  { code: "SA", name: "Saudi Arabia",  flag: "🇸🇦", timezone: "Asia/Riyadh",       currency: "SAR" },
  { code: "QA", name: "Qatar",         flag: "🇶🇦", timezone: "Asia/Qatar",        currency: "QAR" },
  { code: "KW", name: "Kuwait",        flag: "🇰🇼", timezone: "Asia/Kuwait",       currency: "KWD" },
  { code: "BH", name: "Bahrain",       flag: "🇧🇭", timezone: "Asia/Bahrain",      currency: "BHD" },
  { code: "OM", name: "Oman",          flag: "🇴🇲", timezone: "Asia/Muscat",       currency: "OMR" },
  { code: "IL", name: "Israel",        flag: "🇮🇱", timezone: "Asia/Jerusalem",    currency: "ILS" },

  // Asia
  { code: "IN", name: "India",         flag: "🇮🇳", timezone: "Asia/Kolkata",      currency: "INR" },
  { code: "PK", name: "Pakistan",      flag: "🇵🇰", timezone: "Asia/Karachi",      currency: "PKR" },
  { code: "BD", name: "Bangladesh",    flag: "🇧🇩", timezone: "Asia/Dhaka",        currency: "BDT" },
  { code: "LK", name: "Sri Lanka",     flag: "🇱🇰", timezone: "Asia/Colombo",      currency: "LKR" },
  { code: "NP", name: "Nepal",         flag: "🇳🇵", timezone: "Asia/Kathmandu",    currency: "NPR" },
  { code: "SG", name: "Singapore",     flag: "🇸🇬", timezone: "Asia/Singapore",    currency: "SGD" },
  { code: "MY", name: "Malaysia",      flag: "🇲🇾", timezone: "Asia/Kuala_Lumpur", currency: "MYR" },
  { code: "TH", name: "Thailand",      flag: "🇹🇭", timezone: "Asia/Bangkok",      currency: "THB" },
  { code: "ID", name: "Indonesia",     flag: "🇮🇩", timezone: "Asia/Jakarta",      currency: "IDR" },
  { code: "PH", name: "Philippines",   flag: "🇵🇭", timezone: "Asia/Manila",       currency: "PHP" },
  { code: "VN", name: "Vietnam",       flag: "🇻🇳", timezone: "Asia/Ho_Chi_Minh",  currency: "VND" },
  { code: "HK", name: "Hong Kong",     flag: "🇭🇰", timezone: "Asia/Hong_Kong",    currency: "HKD" },
  { code: "TW", name: "Taiwan",        flag: "🇹🇼", timezone: "Asia/Taipei",       currency: "TWD" },
  { code: "JP", name: "Japan",         flag: "🇯🇵", timezone: "Asia/Tokyo",        currency: "JPY" },
  { code: "KR", name: "South Korea",   flag: "🇰🇷", timezone: "Asia/Seoul",        currency: "KRW" },
  { code: "CN", name: "China",         flag: "🇨🇳", timezone: "Asia/Shanghai",     currency: "CNY" },

  // Africa
  { code: "ZA", name: "South Africa",  flag: "🇿🇦", timezone: "Africa/Johannesburg", currency: "ZAR" },
  { code: "NG", name: "Nigeria",       flag: "🇳🇬", timezone: "Africa/Lagos",      currency: "NGN" },
  { code: "KE", name: "Kenya",         flag: "🇰🇪", timezone: "Africa/Nairobi",    currency: "KES" },
  { code: "EG", name: "Egypt",         flag: "🇪🇬", timezone: "Africa/Cairo",      currency: "EGP" },
  { code: "MA", name: "Morocco",       flag: "🇲🇦", timezone: "Africa/Casablanca", currency: "MAD" },
  { code: "GH", name: "Ghana",         flag: "🇬🇭", timezone: "Africa/Accra",      currency: "GHS" },
];

export const COUNTRY_BY_CODE = Object.fromEntries(COUNTRIES.map(c => [c.code, c]));

export const DEFAULT_COUNTRY = "NZ";

/** Lookup helper — returns flag emoji or empty string for unknown codes. */
export function flagForCountry(code) {
  return COUNTRY_BY_CODE[code]?.flag || "";
}

/** Lookup helper — returns the human-readable name. */
export function nameForCountry(code) {
  return COUNTRY_BY_CODE[code]?.name || code || "";
}

/** Returns the country's primary IANA timezone, or browser tz as fallback. */
export function timezoneForCountry(code) {
  if (COUNTRY_BY_CODE[code]?.timezone) return COUNTRY_BY_CODE[code].timezone;
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return "UTC";
  }
}

/** Returns the country's most-common currency for the create-event form. */
export function currencyForCountry(code) {
  return COUNTRY_BY_CODE[code]?.currency || "USD";
}
