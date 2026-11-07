/**
 * Static explanatory text only. All numbers (consumption, prices, findings, scores, savings) come from the backend;
 * Hugo's placeholder figures were removed when the frontend was connected to the engine.
 */
import type { Limitation } from './types';

export const LIMITATIONS: readonly Limitation[] = [
  {
    title: 'Spot price only, not a bill',
    body: 'Costs use the hourly spot price excluding VAT. Retailer markup, network fees, energy tax, VAT and fixed fees are not in the data, so these figures are not what you pay.',
  },
  {
    title: 'Your contract decides the money',
    body: 'Savings in SEK depend on your electricity contract. Moving use to other hours only saves money on an hourly spot contract; with electricity included in rent you save 0 SEK.',
  },
  {
    title: 'Appliance types are inferred',
    body: 'The data has seven unlabelled channels per flat. Names like “fridge-like” are inferred from the load shape and are assumptions.',
  },
  {
    title: 'Four synthetic weeks',
    body: 'Synthetic data for 1–28 Oct 2026. Yearly figures are shown only for persistent equipment or always-on patterns, always as projections with a range. Heating and timing are not extrapolated.',
  },
  {
    title: 'Simulated, not verified',
    body: 'Savings are simulations of what would change if a pattern were acted on. A saving counts as measured only after at least 7 days of new data show it.',
  },
  {
    title: 'Missing readings stay missing',
    body: 'Hours without a reading are left out of sums (never counted as zero) and reported as coverage.',
  },
  {
    title: 'Occupancy is simulated',
    body: 'Whether someone is home comes from a simulated sensor estimate. It is used as context only, not as tracking of people.',
  },
  {
    title: 'Times are Stockholm local time',
    body: 'Clocks went back on 25 October (that day has 25 hours). The data is stored in UTC and shown in local time.',
  },
];
