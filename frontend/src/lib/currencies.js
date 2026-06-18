/**
 * Currency catalog + formatting helpers.
 *
 * The platform is global — organizers pick a currency per event (ISO 4217)
 * and that currency drives display, checkout, and payout totals everywhere.
 * NZD is the default since the platform's primary market is New Zealand.
 *
 * NOTE: Keep this list in sync with Stripe's supported currencies.
 *   https://stripe.com/docs/currencies
 */
export const SUPPORTED_CURRENCIES = [
  { code: "NZD", name: "New Zealand Dollar", symbol: "NZ$", flag: "🇳🇿" },
  { code: "AUD", name: "Australian Dollar",  symbol: "A$",  flag: "🇦🇺" },
  { code: "USD", name: "US Dollar",          symbol: "US$", flag: "🇺🇸" },
  { code: "GBP", name: "British Pound",      symbol: "£",   flag: "🇬🇧" },
  { code: "EUR", name: "Euro",               symbol: "€",   flag: "🇪🇺" },
  { code: "CAD", name: "Canadian Dollar",    symbol: "C$",  flag: "🇨🇦" },
  { code: "SGD", name: "Singapore Dollar",   symbol: "S$",  flag: "🇸🇬" },
  { code: "HKD", name: "Hong Kong Dollar",   symbol: "HK$", flag: "🇭🇰" },
  { code: "JPY", name: "Japanese Yen",       symbol: "¥",   flag: "🇯🇵" },
  { code: "INR", name: "Indian Rupee",       symbol: "₹",   flag: "🇮🇳" },
  { code: "AED", name: "UAE Dirham",         symbol: "د.إ", flag: "🇦🇪" },
  { code: "SAR", name: "Saudi Riyal",        symbol: "﷼",   flag: "🇸🇦" },
  { code: "ZAR", name: "South African Rand", symbol: "R",   flag: "🇿🇦" },
  { code: "BRL", name: "Brazilian Real",     symbol: "R$",  flag: "🇧🇷" },
  { code: "MXN", name: "Mexican Peso",       symbol: "Mex$",flag: "🇲🇽" },
  { code: "CHF", name: "Swiss Franc",        symbol: "CHF", flag: "🇨🇭" },
  { code: "SEK", name: "Swedish Krona",      symbol: "kr",  flag: "🇸🇪" },
  { code: "NOK", name: "Norwegian Krone",    symbol: "kr",  flag: "🇳🇴" },
  { code: "DKK", name: "Danish Krone",       symbol: "kr",  flag: "🇩🇰" },
  { code: "MYR", name: "Malaysian Ringgit",  symbol: "RM",  flag: "🇲🇾" },
  { code: "THB", name: "Thai Baht",          symbol: "฿",   flag: "🇹🇭" },
  { code: "IDR", name: "Indonesian Rupiah",  symbol: "Rp",  flag: "🇮🇩" },
  { code: "PHP", name: "Philippine Peso",    symbol: "₱",   flag: "🇵🇭" },
  { code: "KRW", name: "South Korean Won",   symbol: "₩",   flag: "🇰🇷" },
  { code: "CNY", name: "Chinese Yuan",       symbol: "¥",   flag: "🇨🇳" },
];

export const DEFAULT_CURRENCY = "NZD";

const _byCode = SUPPORTED_CURRENCIES.reduce((m, c) => { m[c.code] = c; return m; }, {});

export function getCurrency(code) {
  if (!code) return _byCode[DEFAULT_CURRENCY];
  return _byCode[code.toUpperCase()] || { code: code.toUpperCase(), symbol: code.toUpperCase() + " ", name: code, flag: "" };
}

/**
 * Format a numeric amount using the currency's locale. Falls back to a manual
 * symbol + fixed-2 when Intl doesn't recognize the code.
 *
 * @param {object} options
 * @param {boolean} [options.free] When true, returns the localized "Free" label
 *   if amount evaluates to 0. Use on public-facing surfaces (event cards, tier
 *   prices, seatmap legend). Keep OFF for accounting surfaces (refunds,
 *   payouts, totals) where "$0.00" carries meaning.
 * @param {string}  [options.freeLabel] Override the literal used when free=true.
 */
export function formatMoney(amount, code, options = {}) {
  const value = Number(amount || 0);
  const { free = false, freeLabel = "Free", ...intlOpts } = options;
  if (free && value === 0) return freeLabel;
  const cur = (code || DEFAULT_CURRENCY).toUpperCase();
  const opts = { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2, ...intlOpts };
  try {
    return new Intl.NumberFormat(undefined, opts).format(value);
  } catch {
    const meta = getCurrency(cur);
    return `${meta.symbol}${value.toFixed(2)}`;
  }
}

/** Just the currency symbol (e.g. "NZ$") — useful as an input adornment. */
export function currencySymbol(code) {
  return getCurrency(code).symbol;
}
