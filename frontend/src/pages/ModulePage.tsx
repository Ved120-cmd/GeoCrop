import { Link } from 'react-router-dom'
import { CheckCircle2, CircleDashed, Hammer } from 'lucide-react'
import { useI18n, type Lang, type TKey } from '../lib/i18n'
import { Container } from '../components/ui'

type ModuleKey = 'predict' | 'advisor' | 'doctor' | 'simulator'

// Honest status, taken from reports/GEOCROP_READINESS_REPORT.md. No placeholder numbers.
const MODULES: Record<ModuleKey, {
  nav: TKey; tone: string
  what: Record<Lang, string>; ready: Record<Lang, string[]>; missing: Record<Lang, string[]>; now?: { to: string; label: Record<Lang, string> }
}> = {
  predict: {
    nav: 'nav_predict', tone: 'bg-sky',
    what: { en: 'Forecast crop water stress 16 and 32 days ahead for each district and farm, with an explanation of which factors drive the forecast.', mr: 'प्रत्येक जिल्हा व शेतासाठी १६ व ३२ दिवस पुढील पाण्याच्या ताणाचा अंदाज, कोणते घटक कारणीभूत आहेत याच्या स्पष्टीकरणासह.' },
    ready: { en: ['MODIS vegetation, land temperature, evapotranspiration 2015–today', 'SMAP soil moisture 2015–today', 'IMD, CHIRPS and IMERG rainfall; NASA POWER weather', 'ECMWF real-time 10-day forecast', 'Monitor feature tables (district time series)'], mr: ['MODIS वनस्पती, तापमान, बाष्पीभवन २०१५–आज', 'SMAP मातीतील ओलावा', 'IMD, CHIRPS, IMERG पाऊस; NASA POWER हवामान', 'ECMWF १० दिवसांचा अंदाज', 'निरीक्षण वैशिष्ट्य सारण्या'] },
    missing: { en: ['ECMWF reforecasts (needed to train without future-weather leakage)', 'Validated crop-stress labels', 'Trained XGBoost/LightGBM models and their evaluation'], mr: ['ECMWF पुनर्पूर्वानुमान (प्रशिक्षणासाठी आवश्यक)', 'पडताळलेली पीक-ताण लेबल्स', 'प्रशिक्षित मॉडेल्स व मूल्यमापन'] },
    now: { to: '/monitor', label: { en: "Today's stress + 10-day outlook is in Monitor", mr: 'आजचा ताण व १० दिवसांचा अंदाज निरीक्षण विभागात' } },
  },
  advisor: {
    nav: 'nav_advisor', tone: 'bg-peach',
    what: { en: 'Suggest suitable crops and sowing windows for your soil, water source and season, with nutrient and integrated pest management guidance.', mr: 'तुमची माती, पाणी स्रोत व हंगामानुसार योग्य पिके व पेरणी कालावधी, पोषण व एकात्मिक कीड व्यवस्थापन मार्गदर्शनासह.' },
    ready: { en: ['District soil profiles (SoilGrids 2.0) and water holding', 'FAO-56 crop water parameters for 12 crops', '38 official NIPHM IPM packages; CIB&RC pesticide label claims', 'District crop statistics (partial)'], mr: ['जिल्हा माती प्रोफाइल', '१२ पिकांसाठी FAO-56 पाणी मापदंड', '३८ अधिकृत IPM पॅकेजेस; CIB&RC लेबल दावे', 'जिल्हा पीक आकडेवारी (अंशतः)'] },
    missing: { en: ['Maharashtra crop calendar from agricultural universities (MPKV, VNMKV, PDKV, DBSKKV)', 'Crop requirement tables with sources', 'Soil Health Card laboratory data'], mr: ['कृषी विद्यापीठांचे पीक दिनदर्शिका', 'स्रोतांसह पीक आवश्यकता सारण्या', 'मृदा आरोग्य पत्रिका प्रयोगशाळा माहिती'] },
    now: { to: '/soil', label: { en: 'See your district soil profile', mr: 'तुमच्या जिल्ह्याचे माती प्रोफाइल पहा' } },
  },
  doctor: {
    nav: 'nav_doctor', tone: 'bg-sage',
    what: { en: 'Take a photo of a leaf or pest; get the likely disease or pest, with official integrated pest management advice and registered control options.', mr: 'पान किंवा किडीचा फोटो घ्या; संभाव्य रोग/कीड आणि अधिकृत एकात्मिक कीड व्यवस्थापन सल्ला मिळवा.' },
    ready: { en: ['PlantVillage: 54,305 images, 38 classes', 'PlantDoc: 2,573 field images, 29 classes', 'Official IPM packages and CIB&RC registered uses'], mr: ['PlantVillage: ५४,३०५ चित्रे', 'PlantDoc: २,५७३ शेत चित्रे', 'अधिकृत IPM पॅकेजेस'] },
    missing: { en: ['IP102 insect-pest dataset (manual download)', 'Photos from Maharashtra fields', 'Trained and evaluated image model'], mr: ['IP102 कीड माहितीसंच', 'महाराष्ट्रातील शेतांचे फोटो', 'प्रशिक्षित प्रतिमा मॉडेल'] },
  },
  simulator: {
    nav: 'nav_sim', tone: 'bg-ash',
    what: { en: 'Simulate yield and water use for "what if" choices: sowing date, irrigation schedule, crop variety, using FAO AquaCrop 7.3.', mr: '"असे केले तर" निवडींसाठी उत्पादन व पाणी वापराचे सिम्युलेशन: पेरणी तारीख, सिंचन वेळापत्रक, वाण (FAO AquaCrop 7.3).' },
    ready: { en: ['Official FAO AquaCrop 7.3 Python engine (checksum verified, runs)', '29 FAO crop files, 14 soil files', 'Daily weather and reference ET for every district'], mr: ['अधिकृत FAO AquaCrop 7.3 इंजिन', '२९ पीक फायली, १४ माती फायली', 'प्रत्येक जिल्ह्यासाठी दैनिक हवामान'] },
    missing: { en: ['Project-file builder for AquaCrop runs', 'Calibration and validation data from Maharashtra field trials'], mr: ['AquaCrop प्रकल्प फाइल निर्मिती', 'महाराष्ट्रातील क्षेत्र चाचण्यांचे कॅलिब्रेशन माहिती'] },
  },
}

export default function ModulePage({ module }: { module: ModuleKey }) {
  const { t, lang } = useI18n()
  const m = MODULES[module]
  return (
    <Container className="py-10 md:py-14">
      <div className={`rounded-[30px] ${m.tone} p-8 md:p-12`}>
        <span className="badge bg-white text-ink"><Hammer size={12} /> {t('in_dev')}</span>
        <h1 className="mt-4 text-[45px] md:text-[57px]">{t(m.nav)}</h1>
        <p className="mt-4 max-w-[60ch] text-[17px] text-graphite"><strong className="text-ink">{t('what_it_will_do')}:</strong> {m.what[lang]}</p>
        {m.now && <Link to={m.now.to} className="btn-primary mt-6">{t('available_now')}: {m.now.label[lang]}</Link>}
      </div>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="card">
          <h2 className="text-[28px]">{t('data_ready')}</h2>
          <ul className="mt-4 space-y-2.5 text-[15px]">
            {m.ready[lang].map((r) => <li key={r} className="flex gap-2.5"><CheckCircle2 size={18} className="mt-0.5 shrink-0 text-forest" /> {r}</li>)}
          </ul>
        </div>
        <div className="card">
          <h2 className="text-[28px]">{t('data_missing')}</h2>
          <ul className="mt-4 space-y-2.5 text-[15px]">
            {m.missing[lang].map((r) => <li key={r} className="flex gap-2.5"><CircleDashed size={18} className="mt-0.5 shrink-0 text-pewter" /> {r}</li>)}
          </ul>
        </div>
      </div>
    </Container>
  )
}
