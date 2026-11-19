// Colour encodings. Validated with the dataviz palette script on the white card surface:
//   dry arm  #eda07a #d0683d #9e3f1e  (ordinal, one hue, monotone, light end 2.12:1)  -> PASS
//   wet arm  #86b6ef #3987e5 #1c5cab  (ordinal, one hue, monotone, light end 2.11:1)  -> PASS
// Stress severity reuses the dry arm (stress = drying) with sage for "no stress".
// Every class is ALSO shown as a text label (and icon where relevant): colour never carries meaning alone.

export const DRY = ['#eda07a', '#d0683d', '#9e3f1e']
export const WET = ['#86b6ef', '#3987e5', '#1c5cab']
export const NEUTRAL = '#e9e7dd'
export const NO_DATA = '#ffffff'
export const OK = '#e6ecd5' // sage

export interface Bin { key: string; color: string; label: string; label_mr: string; textDark: boolean }

export const STRESS_BINS: Bin[] = [
  { key: 'none', color: OK, label: 'No stress', label_mr: 'ताण नाही', textDark: true },
  { key: 'mild', color: DRY[0], label: 'Mild', label_mr: 'सौम्य', textDark: true },
  { key: 'moderate', color: DRY[1], label: 'Moderate', label_mr: 'मध्यम', textDark: false },
  { key: 'severe', color: DRY[2], label: 'Severe', label_mr: 'तीव्र', textDark: false },
]

// Diverging dry <-> wet, 7 classes (3 + neutral + 3)
const div = (labels: [string, string][]): Bin[] =>
  [DRY[2], DRY[1], DRY[0], NEUTRAL, WET[0], WET[1], WET[2]].map((c, i) => ({
    key: labels[i][0], color: c, label: labels[i][0], label_mr: labels[i][1], textDark: i >= 2 && i <= 4,
  }))

export const SPI_BINS = div([
  ['Extremely dry', 'अतिशय कोरडे'], ['Severely dry', 'तीव्र कोरडे'], ['Moderately dry', 'मध्यम कोरडे'], ['Near normal', 'सामान्य'],
  ['Moderately wet', 'मध्यम ओले'], ['Very wet', 'खूप ओले'], ['Extremely wet', 'अतिशय ओले'],
])

export function spiBin(v: number | null | undefined): Bin | null {
  if (v == null || Number.isNaN(v)) return null
  const i = v <= -2 ? 0 : v <= -1.5 ? 1 : v <= -1 ? 2 : v < 1 ? 3 : v < 1.5 ? 4 : v < 2 ? 5 : 6
  return SPI_BINS[i]
}

export const SM_BINS = div([
  ['≤5th pct · exceptionally dry', '≤५ · अपवादात्मक कोरडे'], ['5–10th · very dry', '५–१० · खूप कोरडे'], ['10–30th · dry', '१०–३० · कोरडे'],
  ['30–70th · normal', '३०–७० · सामान्य'], ['70–90th · wet', '७०–९० · ओले'], ['90–95th · very wet', '९०–९५ · खूप ओले'], ['≥95th · exceptionally wet', '≥९५ · अपवादात्मक ओले'],
])
export function smBin(p: number | null | undefined): Bin | null {
  if (p == null || Number.isNaN(p)) return null
  const i = p <= 5 ? 0 : p <= 10 ? 1 : p <= 30 ? 2 : p < 70 ? 3 : p < 90 ? 4 : p < 95 ? 5 : 6
  return SM_BINS[i]
}

export const DEPARTURE_BINS = div([
  ['No rain / large deficient (≤ −60%)', 'मोठी तूट (≤ −६०%)'], ['Deficient (−59 to −40%)', 'तूट (−५९ ते −४०%)'], ['Deficient (−39 to −20%)', 'तूट (−३९ ते −२०%)'],
  ['Normal (−19 to +19%)', 'सामान्य (−१९ ते +१९%)'], ['Excess (+20 to +39%)', 'जास्त (+२० ते +३९%)'], ['Excess (+40 to +59%)', 'जास्त (+४० ते +५९%)'], ['Large excess (≥ +60%)', 'खूप जास्त (≥ +६०%)'],
])
export function departureBin(v: number | null | undefined): Bin | null {
  if (v == null || Number.isNaN(v)) return null
  const i = v <= -60 ? 0 : v <= -40 ? 1 : v <= -20 ? 2 : v < 20 ? 3 : v < 40 ? 4 : v < 60 ? 5 : 6
  return DEPARTURE_BINS[i]
}

export const VHI_BINS: Bin[] = [
  { key: 'no stress', color: OK, label: 'No stress (VHI ≥ 40)', label_mr: 'ताण नाही (≥ ४०)', textDark: true },
  { key: 'mild', color: DRY[0], label: 'Mild (30–40)', label_mr: 'सौम्य (३०–४०)', textDark: true },
  { key: 'moderate', color: DRY[1], label: 'Moderate (20–30)', label_mr: 'मध्यम (२०–३०)', textDark: false },
  { key: 'severe', color: DRY[2], label: 'Severe / extreme (< 20)', label_mr: 'तीव्र (< २०)', textDark: false },
]
export function vhiBin(v: number | null | undefined): Bin | null {
  if (v == null || Number.isNaN(v)) return null
  return VHI_BINS[v >= 40 ? 0 : v >= 30 ? 1 : v >= 20 ? 2 : 3]
}

export const ESI_BINS = div([
  ['z ≤ −2 · extreme', 'z ≤ −२'], ['−2 to −1.5', '−२ ते −१.५'], ['−1.5 to −0.5', '−१.५ ते −०.५'], ['near normal', 'सामान्य'],
  ['0.5 to 1.5', '०.५ ते १.५'], ['1.5 to 2', '१.५ ते २'], ['z ≥ 2', 'z ≥ २'],
])
export function esiBin(z: number | null | undefined): Bin | null {
  if (z == null || Number.isNaN(z)) return null
  const i = z <= -2 ? 0 : z <= -1.5 ? 1 : z <= -0.5 ? 2 : z < 0.5 ? 3 : z < 1.5 ? 4 : z < 2 ? 5 : 6
  return ESI_BINS[i]
}

export function stressBin(s: string | null | undefined): Bin | null {
  return STRESS_BINS.find((b) => b.key === s) ?? null
}
