import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

// Marathi strings were drafted by the developer and MUST be reviewed by a native speaker before field use.
export type Lang = 'en' | 'mr'

const en = {
  appName: 'geocrop', tagline: 'Crop intelligence for Maharashtra',
  nav_monitor: 'Monitor', nav_predict: 'Predict', nav_soil: 'Soil', nav_advisor: 'Crop Advisor', nav_doctor: 'Plant Doctor', nav_sim: 'Farm Simulator',
  nav_myfarm: 'My farm', nav_profile: 'Profile', menu: 'Menu', close: 'Close',
  hero_title: 'Know what your fields need, before they show it.',
  hero_body: 'Satellite, weather and soil data for every district of Maharashtra, turned into clear signals about crop water stress, drought and soil, for your farm.',
  im_farmer: "I'm a farmer", explore: 'Explore the map', scroll: 'Scroll to explore',
  how_title: 'How GeoCrop works', how_1t: 'Watches from space', how_1: 'NDVI, land temperature, evapotranspiration and soil moisture from NASA satellites, every few days.',
  how_2t: 'Reads the weather', how_2: 'IMD gauge rainfall, satellite rain, and a 10-day ECMWF forecast for every district.',
  how_3t: 'Estimates stress today', how_3: 'A water-balance model shows how dry the root zone is now and how soon a crop may be stressed.',
  how_4t: 'Honest about uncertainty', how_4: 'Every number says if it is observed, estimated, provisional or forecast, and how old it is.',
  // onboarding
  ob_title: 'Tell us about your farm', ob_sub: 'This takes about two minutes. You can change it any time.',
  step_you: 'About you', step_location: 'Location', step_farm: 'Farm & crops', step_review: 'Review',
  name: 'Your name', phone: 'Mobile number (optional)', phone_help: 'Only stored on this GeoCrop server. Not shared.', language: 'Preferred language',
  state: 'State', district: 'District', choose_district: 'Choose your district', taluka: 'Taluka', village: 'Village', region: 'Region',
  pin_title: 'Mark your farm on the map', pin_help: 'Tap the map where your field is. This lets GeoCrop give estimates for your exact location.',
  pin_mismatch: 'This pin is in {d}, not the district you chose.', pin_outside: 'This pin is outside Maharashtra.', pin_ok: 'Pin is in {d}.',
  use_my_location: 'Use my location', farm_name: 'Farm name (optional)', area: 'Farm area', unit_acre: 'acres', unit_hectare: 'hectares', unit_guntha: 'guntha',
  irrigation: 'Main water source', soil_type: 'Soil type (as you know it)',
  irr_rainfed: 'Rainfed (no irrigation)', irr_well: 'Open well', irr_borewell: 'Borewell', irr_canal: 'Canal', irr_tank: 'Tank / pond', irr_river: 'River lift', irr_drip: 'Drip', irr_sprinkler: 'Sprinkler', irr_other: 'Other',
  soil_black: 'Black (regur)', soil_red: 'Red', soil_laterite: 'Laterite', soil_alluvial: 'Alluvial', soil_sandy: 'Sandy', soil_unknown: "Don't know",
  crops_title: 'Crops this year', add_crop: 'Add crop', crop: 'Crop', season: 'Season', sowing_date: 'Sowing date', other_crop: 'Crop name', remove: 'Remove',
  s_kharif: 'Kharif', s_rabi: 'Rabi', s_summer: 'Summer', s_annual: 'Annual / perennial',
  stress_supported: 'Daily stress estimate available', stress_unsupported: 'Stress estimate not available for this crop yet',
  back: 'Back', next: 'Next', save: 'Save and continue', saving: 'Saving…', edit: 'Edit',
  required: 'Required', review_title: 'Check your details',
  // monitor
  mon_title: 'Maharashtra crop monitor', mon_sub: 'Choose an indicator, then a region or district.',
  ind_stress: "Today's water stress", ind_vhi: 'Vegetation health', ind_sm: 'Soil moisture', ind_spi: 'Drought index (SPI-3)', ind_dep: 'Monsoon rainfall', ind_esi: 'Crop water use',
  ind_stress_d: 'Estimated root-zone water stress today (model estimate).', ind_vhi_d: 'Satellite Vegetation Health Index (NDVI + land temperature).',
  ind_sm_d: 'SMAP root-zone soil moisture, percentile vs 2015–2024.', ind_spi_d: '3-month Standardised Precipitation Index vs 1991–2020.',
  ind_dep_d: 'Rain since 1 June vs the 1991–2020 normal.', ind_esi_d: 'Actual vs potential evapotranspiration, anomaly.',
  all_mh: 'All Maharashtra', legend: 'Legend', no_data: 'No data', as_of: 'as of', provisional: 'provisional', estimate: 'estimate', forecast: 'forecast',
  districts_ranked: 'Districts', sort_worst: 'Most stressed first', view_district: 'View district', alerts: 'districts need attention',
  data_freshness: 'Data freshness', last_update: 'Last update',
  // district
  status_now: 'Current status', trends: 'Trends', next_10: 'Next 10 days', depletion: 'Root-zone water used', days_until_stress: 'Days until stress',
  stressed_now: 'Already stressed', no_stress_10: 'No stress expected in 10 days', ndvi_vs_normal: 'Vegetation (NDVI) this year vs normal',
  sm_trend: 'Soil moisture percentile, last 120 days', rain_vs_normal: 'Monsoon rain: this year vs normal', this_year: 'This year', normal: 'Normal', observed: 'Observed',
  my_farm_here: 'Your farm is in this district', open_my_farm: 'Open my farm', back_to_map: 'Back to map', in_region: 'Districts in {r}',
  what_this_means: 'What this means', methods: 'How this is calculated',
  // farm
  farm_title: 'My farm', farm_estimate: 'Water stress for your crop', log_irrigation: 'Log irrigation', amount_mm: 'Amount (mm)', date: 'Date', add: 'Add',
  irr_log: 'Irrigation log', irr_none: 'No irrigation logged. Without it, stress for irrigated fields is overstated.',
  mm_hint: '1 hour of a 5 HP pump on 1 acre is roughly 15–25 mm. A full flood irrigation is often 50–75 mm.',
  no_profile: 'Create your farm profile to see estimates for your own field.', create_profile: 'Create profile',
  // modules
  in_dev: 'In development', what_it_will_do: 'What it will do', data_ready: 'Data ready', data_missing: 'Still needed', available_now: 'Available now',
  // soil
  soil_title: 'Soil intelligence', soil_sub: 'District soil profile from global soil maps. Use Soil Health Card lab results for fertilizer decisions.',
  depth: 'Depth', texture: 'Texture', water_holding: 'Water holding', fc: 'Field capacity', wp: 'Wilting point', awc: 'Available water',
  // misc
  loading: 'Loading…', error: 'Could not load data', retry: 'Retry', mr_review: 'Marathi text is a draft awaiting native-speaker review.',
  footer_data: 'Data: NASA MODIS, SMAP & GPM via Google Earth Engine · IMD · CHIRPS · NASA POWER · ECMWF (CC BY 4.0) · ISRIC SoilGrids · geoBoundaries',
  footer_note: 'GeoCrop gives estimates to support decisions. It does not replace advice from your agriculture officer.',
}

type Dict = typeof en
const mr: Dict = {
  appName: 'geocrop', tagline: 'महाराष्ट्रासाठी पीक माहिती',
  nav_monitor: 'निरीक्षण', nav_predict: 'अंदाज', nav_soil: 'माती', nav_advisor: 'पीक सल्ला', nav_doctor: 'वनस्पती डॉक्टर', nav_sim: 'शेत सिम्युलेटर',
  nav_myfarm: 'माझे शेत', nav_profile: 'प्रोफाइल', menu: 'मेनू', close: 'बंद करा',
  hero_title: 'शेताला काय हवे आहे ते आधीच जाणून घ्या.',
  hero_body: 'महाराष्ट्रातील प्रत्येक जिल्ह्यासाठी उपग्रह, हवामान आणि मातीची माहिती — पिकावरील पाण्याचा ताण, दुष्काळ आणि मातीबद्दल स्पष्ट संकेत.',
  im_farmer: 'मी शेतकरी आहे', explore: 'नकाशा पहा', scroll: 'खाली पहा',
  how_title: 'GeoCrop कसे काम करते', how_1t: 'अवकाशातून निरीक्षण', how_1: 'NASA उपग्रहांकडून दर काही दिवसांनी NDVI, जमिनीचे तापमान, बाष्पीभवन आणि मातीतील ओलावा.',
  how_2t: 'हवामानाची माहिती', how_2: 'IMD पर्जन्यमापक, उपग्रह पाऊस आणि प्रत्येक जिल्ह्यासाठी १० दिवसांचा ECMWF अंदाज.',
  how_3t: 'आजचा ताण अंदाज', how_3: 'पाणी-संतुलन मॉडेल मुळांच्या भागात किती कोरडेपणा आहे आणि पिकावर ताण कधी येईल ते दाखवते.',
  how_4t: 'अनिश्चिततेबाबत प्रामाणिक', how_4: 'प्रत्येक आकडा निरीक्षण, अंदाज, तात्पुरता की पूर्वानुमान आहे आणि किती जुना आहे ते सांगतो.',
  ob_title: 'तुमच्या शेताबद्दल सांगा', ob_sub: 'यासाठी सुमारे दोन मिनिटे लागतात. नंतर कधीही बदलू शकता.',
  step_you: 'तुमच्याबद्दल', step_location: 'ठिकाण', step_farm: 'शेत व पिके', step_review: 'तपासा',
  name: 'तुमचे नाव', phone: 'मोबाइल नंबर (ऐच्छिक)', phone_help: 'फक्त या GeoCrop सर्व्हरवर साठवले जाते. कोणालाही दिले जात नाही.', language: 'पसंतीची भाषा',
  state: 'राज्य', district: 'जिल्हा', choose_district: 'तुमचा जिल्हा निवडा', taluka: 'तालुका', village: 'गाव', region: 'विभाग',
  pin_title: 'नकाशावर तुमचे शेत दाखवा', pin_help: 'तुमचे शेत जिथे आहे तिथे नकाशावर टॅप करा. त्यामुळे अचूक ठिकाणासाठी अंदाज देता येतो.',
  pin_mismatch: 'ही खूण {d} मध्ये आहे, तुम्ही निवडलेल्या जिल्ह्यात नाही.', pin_outside: 'ही खूण महाराष्ट्राबाहेर आहे.', pin_ok: 'खूण {d} मध्ये आहे.',
  use_my_location: 'माझे ठिकाण वापरा', farm_name: 'शेताचे नाव (ऐच्छिक)', area: 'शेताचे क्षेत्र', unit_acre: 'एकर', unit_hectare: 'हेक्टर', unit_guntha: 'गुंठा',
  irrigation: 'पाण्याचा मुख्य स्रोत', soil_type: 'मातीचा प्रकार (तुमच्या माहितीनुसार)',
  irr_rainfed: 'कोरडवाहू (सिंचन नाही)', irr_well: 'विहीर', irr_borewell: 'बोअरवेल', irr_canal: 'कालवा', irr_tank: 'तलाव / शेततळे', irr_river: 'नदी उपसा', irr_drip: 'ठिबक', irr_sprinkler: 'तुषार', irr_other: 'इतर',
  soil_black: 'काळी (रेगुर)', soil_red: 'लाल', soil_laterite: 'जांभा', soil_alluvial: 'गाळाची', soil_sandy: 'वालुकामय', soil_unknown: 'माहीत नाही',
  crops_title: 'या वर्षीची पिके', add_crop: 'पीक जोडा', crop: 'पीक', season: 'हंगाम', sowing_date: 'पेरणीची तारीख', other_crop: 'पिकाचे नाव', remove: 'काढा',
  s_kharif: 'खरीप', s_rabi: 'रब्बी', s_summer: 'उन्हाळी', s_annual: 'वार्षिक / बहुवार्षिक',
  stress_supported: 'दैनिक ताण अंदाज उपलब्ध', stress_unsupported: 'या पिकासाठी ताण अंदाज अजून उपलब्ध नाही',
  back: 'मागे', next: 'पुढे', save: 'जतन करा व पुढे चला', saving: 'जतन होत आहे…', edit: 'बदला',
  required: 'आवश्यक', review_title: 'तुमची माहिती तपासा',
  mon_title: 'महाराष्ट्र पीक निरीक्षण', mon_sub: 'निर्देशक निवडा, मग विभाग किंवा जिल्हा.',
  ind_stress: 'आजचा पाण्याचा ताण', ind_vhi: 'वनस्पती आरोग्य', ind_sm: 'मातीतील ओलावा', ind_spi: 'दुष्काळ निर्देशांक (SPI-3)', ind_dep: 'मान्सून पाऊस', ind_esi: 'पिकाचा पाणी वापर',
  ind_stress_d: 'मुळांच्या भागातील आजचा अंदाजित पाण्याचा ताण (मॉडेल अंदाज).', ind_vhi_d: 'उपग्रह वनस्पती आरोग्य निर्देशांक (NDVI + जमिनीचे तापमान).',
  ind_sm_d: 'SMAP मुळांच्या भागातील ओलावा, २०१५–२०२४ च्या तुलनेत.', ind_spi_d: '१९९१–२०२० च्या तुलनेत ३ महिन्यांचा पर्जन्य निर्देशांक.',
  ind_dep_d: '१ जूनपासूनचा पाऊस, १९९१–२०२० च्या सरासरीच्या तुलनेत.', ind_esi_d: 'प्रत्यक्ष व संभाव्य बाष्पीभवन, सरासरीपासून फरक.',
  all_mh: 'संपूर्ण महाराष्ट्र', legend: 'सूची', no_data: 'माहिती नाही', as_of: 'दिनांक', provisional: 'तात्पुरते', estimate: 'अंदाज', forecast: 'पूर्वानुमान',
  districts_ranked: 'जिल्हे', sort_worst: 'सर्वाधिक ताण आधी', view_district: 'जिल्हा पहा', alerts: 'जिल्ह्यांकडे लक्ष देणे आवश्यक',
  data_freshness: 'माहितीची ताजेपणा', last_update: 'शेवटचे अद्यतन',
  status_now: 'सध्याची स्थिती', trends: 'कल', next_10: 'पुढील १० दिवस', depletion: 'मुळांच्या भागातील वापरलेले पाणी', days_until_stress: 'ताण येण्यास दिवस',
  stressed_now: 'आधीच ताणाखाली', no_stress_10: '१० दिवसांत ताण अपेक्षित नाही', ndvi_vs_normal: 'वनस्पती (NDVI) या वर्षी वि. सरासरी',
  sm_trend: 'मातीतील ओलावा, मागील १२० दिवस', rain_vs_normal: 'मान्सून पाऊस: या वर्षी वि. सरासरी', this_year: 'या वर्षी', normal: 'सरासरी', observed: 'निरीक्षित',
  my_farm_here: 'तुमचे शेत या जिल्ह्यात आहे', open_my_farm: 'माझे शेत उघडा', back_to_map: 'नकाशाकडे परत', in_region: '{r} मधील जिल्हे',
  what_this_means: 'याचा अर्थ', methods: 'हे कसे मोजले जाते',
  farm_title: 'माझे शेत', farm_estimate: 'तुमच्या पिकावरील पाण्याचा ताण', log_irrigation: 'पाणी दिल्याची नोंद', amount_mm: 'प्रमाण (मिमी)', date: 'तारीख', add: 'जोडा',
  irr_log: 'सिंचन नोंद', irr_none: 'कोणतीही सिंचन नोंद नाही. नोंद नसल्यास बागायती शेतासाठी ताण जास्त दाखवला जातो.',
  mm_hint: '१ एकरावर ५ HP पंप १ तास ≈ १५–२५ मिमी. पूर्ण पाटपाणी साधारण ५०–७५ मिमी.',
  no_profile: 'तुमच्या शेतासाठी अंदाज पाहण्यासाठी प्रोफाइल तयार करा.', create_profile: 'प्रोफाइल तयार करा',
  in_dev: 'विकसनाधीन', what_it_will_do: 'हे काय करेल', data_ready: 'तयार माहिती', data_missing: 'अजून आवश्यक', available_now: 'आता उपलब्ध',
  soil_title: 'माती माहिती', soil_sub: 'जागतिक माती नकाशांवरून जिल्ह्याचे माती प्रोफाइल. खत निर्णयांसाठी मृदा आरोग्य पत्रिकेचे निकाल वापरा.',
  depth: 'खोली', texture: 'पोत', water_holding: 'पाणी धारण क्षमता', fc: 'क्षेत्र क्षमता', wp: 'कोमेजण्याचा बिंदू', awc: 'उपलब्ध पाणी',
  loading: 'लोड होत आहे…', error: 'माहिती लोड झाली नाही', retry: 'पुन्हा प्रयत्न करा', mr_review: 'मराठी मजकूर मसुदा आहे; मातृभाषक तपासणी बाकी आहे.',
  footer_data: 'माहिती: NASA MODIS, SMAP व GPM (Google Earth Engine) · IMD · CHIRPS · NASA POWER · ECMWF (CC BY 4.0) · ISRIC SoilGrids · geoBoundaries',
  footer_note: 'GeoCrop निर्णयासाठी अंदाज देते. कृषी अधिकाऱ्यांच्या सल्ल्याला हा पर्याय नाही.',
}

export type TKey = keyof Dict
const DICTS: Record<Lang, Dict> = { en, mr }

interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: (k: TKey, vars?: Record<string, string | number>) => string }
const I18n = createContext<Ctx | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try { return (localStorage.getItem('geocrop.lang') as Lang) || 'en' } catch { return 'en' }
  })
  useEffect(() => {
    try { localStorage.setItem('geocrop.lang', lang) } catch { /* private mode */ }
    document.documentElement.lang = lang === 'mr' ? 'mr' : 'en'
  }, [lang])
  const t = (k: TKey, vars?: Record<string, string | number>) => {
    let s = DICTS[lang][k] ?? en[k]
    if (vars) for (const [vk, vv] of Object.entries(vars)) s = s.replace(`{${vk}}`, String(vv))
    return s
  }
  return <I18n.Provider value={{ lang, setLang, t }}>{children}</I18n.Provider>
}

export function useI18n() {
  const c = useContext(I18n)
  if (!c) throw new Error('useI18n outside provider')
  return c
}

/** Pick an English/Marathi pair. */
export function pick(lang: Lang, en_: string, mr_?: string | null) {
  return lang === 'mr' && mr_ ? mr_ : en_
}
