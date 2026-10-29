import { createContext, useContext, useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me'

const LanguageContext = createContext()

export const TRANSLATIONS = {
  'en-NZ': {
    // Nav
    brand: 'SMART MIRROR',
    dashboard: 'DASHBOARD',
    settings: 'SETTINGS',
    admin: 'ADMIN ANALYTICS',
    privacy: 'PRIVACY POLICY',
    terms: 'TERMS & CONDITIONS',

    // Notices
    notices: 'NOTICES',
    notices_active: 'ACTIVE NOTICES',
    today: 'TODAY',
    fetched: 'FETCHED',
    search_placeholder: 'SEARCH NOTICES...',
    clear: 'CLEAR',
    year: 'YEAR',
    all: 'ALL',
    no_notices: 'NO NOTICES AVAILABLE TODAY.',
    no_matches: 'NO NOTICES MATCH CURRENT FILTERS.',
    filter_settings: 'DISPLAY & FILTER SETTINGS',
    click_to_configure: 'CLICK TO CONFIGURE DISPLAY & FILTERS',
    back_to_notices: 'BACK TO NOTICES',
    motion_speed: 'MOTION & SEQUENCING',
    speed: 'SPEED',
    slow: 'SLOW',
    normal: 'NORMAL',
    fast: 'FAST',
    form_class: 'CLASS NAME / FORM CLASS',
    keyword_boost: 'KEYWORD BOOST (DRAG TO REORDER)',
    keyword_placeholder: 'TYPE KEYWORD AND PRESS ENTER',
    category_order: 'CATEGORY PRIORITY ORDER',
    category_order_desc: 'Drag categories to prioritize display sequence.',
    apply_sync: 'APPLY & SYNC TO MIRROR',
    applied: 'APPLIED & SYNCED',
    apply_changes: 'APPLY CHANGES',
    changes_applied: 'CHANGES APPLIED',
    close: 'CLOSE',
    full_text: 'FULL NOTICE TEXT',
    read: 'READ →',
    read_notice: 'READ NOTICE',
    see: 'SEE',
    click_anywhere_close: 'CLICK ANYWHERE TO RETURN',

    // Timetable
    current_class: 'CURRENT CLASS',
    next_class: 'NEXT CLASS',
    room: 'ROOM',
    ends: 'ENDS',
    left: 'LEFT',
    interval: 'INTERVAL (RECESS)',
    lunch: 'LUNCHTIME BREAK',
    morning_interval: 'Morning Interval',
    lunch_break: 'Lunch Break',
    no_timetable: 'NO TIMETABLE CONFIGURED',
    link_kamar_prompt: 'LINK KAMAR .ICS TO SYNC PERIODS AND COUNTDOWN',
    set_up_timetable: 'SET UP TIMETABLE',
    sync_timetable: 'SYNC TIMETABLE',
    save_timetable: 'SAVE TIMETABLE',
    paste_ics_link: 'PASTE YOUR .ICS LINK HERE',
    slideshow_step: 'STEP',
    prev: 'PREV',
    next: 'NEXT',
    library_loans: 'LIBRARY & BOOK LOANS',
    due: 'DUE',
    overdue: 'OVERDUE',
    use_sample_link: 'USE SAMPLE LINK',
    timetable_settings: 'TIMETABLE SETTINGS',
    back_to_timetable: 'BACK TO TIMETABLE',
    periods: 'PERIODS',
    schedule_view: 'SCHEDULE VIEW',
    display_options: 'DISPLAY OPTIONS',
    show_breaks: 'SHOW INTERVAL & LUNCH BREAKS',
    highlight_current: 'HIGHLIGHT CURRENT PERIOD',
    calendar_feed: 'CALENDAR FEED SOURCE',
    reconfigure_link: 'CHANGE .ICS LINK',
    unlink_timetable: 'UNLINK TIMETABLE',
    // The timetable comes from KAMAR through the student ID (not a calendar link).
    // Only English so far: Māori falls back to these until they are translated.
    no_timetable_yet: 'NO TIMETABLE YET',
    timetable_from_kamar: 'YOUR TIMETABLE COMES FROM KAMAR. LINK YOUR STUDENT ID IN SETTINGS AND IT APPEARS AUTOMATICALLY',
    open_settings: 'OPEN SETTINGS',
    timetable_source: 'TIMETABLE SOURCE',
    timetable_kamar: 'KAMAR',

    // Onboarding Modal
    setup_guide: 'SETUP GUIDE',
    setup_desc: 'Complete your mirror profile to activate automatic recognition and schedule sync.',
    barcode_step: '1. LINK STUDENT ID BARCODE',
    face_step: '2. ENROLL FACE BIOMETRICS (OPTIONAL)',
    timetable_step: '3. CONNECT KAMAR TIMETABLE',
    dont_show_again: "DON'T SHOW THIS AGAIN",
    get_started: 'CONTINUE',
    link_btn: 'LINK',
    enroll_btn: 'ENROLL',
    connect_btn: 'SET UP',
    optional_tag: 'OPTIONAL',

    // Settings page
    account_mgmt: 'ACCOUNT & IDENTITY MANAGEMENT',
    preferences_subtitle: 'LINK STUDENT ID BARCODE, BIOMETRICS, REGIONAL LANGUAGE, AND PRIVACY SETTINGS',
    authenticated: 'AUTHENTICATED',
    student_id_title: 'STUDENT ID BARCODE LINK',
    student_id_desc: 'Your student ID number acts as your physical sign-in key and verified identity anchor.',
    active_student_id: 'ACTIVE STUDENT ID NUMBER',
    change_id: 'CHANGE ID',
    unlink: 'UNLINK',
    no_barcode_yet: 'NO STUDENT ID LINKED YET',
    no_barcode_desc: 'Scanning your student ID card or entering your student ID number links your account and unlocks biometric face registration.',
    link_barcode_btn: 'LINK STUDENT ID BARCODE',
    checking: 'CHECKING...',
    face_recognition_title: 'BIOMETRIC FACE RECOGNITION (OPTIONAL)',
    face_recognition_desc: 'Walk up to the mirror and get instantly recognized without touching the glass or scanning a card.',
    face_locked_title: 'FACE SCAN LOCKED',
    face_locked_desc: 'Student ID barcode must be linked first to prevent misidentification.',
    link_barcode_unlock: 'LINK BARCODE TO UNLOCK',
    face_registered_title: 'FACE SCAN REGISTERED',
    delete_rescan: 'DELETE & RE-SCAN',
    ready_face_title: 'READY FOR FACE SCAN (OPTIONAL)',
    ready_face_desc: 'Capture 10 rapid webcam frames to train your biometric model on the server.',
    register_face_btn: 'REGISTER FACE SCAN',
    regional_lang_theme: 'REGIONAL LANGUAGE & THEME',
    language_label: 'REGIONAL LANGUAGE / REO',
    theme_label: 'MIRROR CONTRAST THEME',
    session_control: 'SESSION CONTROL',
    sign_out: 'SIGN OUT OF ACCOUNT',
    active_tag: 'ACTIVE',
    select_tag: 'SELECT',
    drag_to_reorder: 'DRAG TO REORDER',
    reset: 'RESET',

    // Login page
    student_portal_auth: 'STUDENT PORTAL AUTHENTICATION',
    sign_in_register: 'SIGN IN / REGISTER',
    login_terms_prefix: 'By signing up or logging in, you agree to our',
    login_optional_quote: '"Using the mirror and personalising it by signing up is entirely optional."',

    // Categories
    cat_General: 'General',
    cat_Sports: 'Sports',
    cat_Meetings: 'Meetings',
    cat_Academic: 'Academic',
    cat_Careers: 'Careers',
    cat_ArtsCulture: 'Arts & Culture',
    cat_Service: 'Service',
  },
  'mi-NZ': {
    // Nav
    brand: 'WHAKAATA ATAMAI',
    dashboard: 'PAPATOHU',
    settings: 'TAUTUHINGA',
    admin: 'TĀTARITANGA',
    privacy: 'KAUPAPA TŪMATAITI',
    terms: 'NGĀ KAWENATA',

    // Notices
    notices: 'NGĀ PĀNUI',
    notices_active: 'NGĀ PĀNUI E HIKOI ANA',
    today: 'I TĒNEI RĀ',
    fetched: 'KUA TIKINA',
    search_placeholder: 'RAPUA HE PĀNUI...',
    clear: 'WHAKAKORE',
    year: 'TAU',
    all: 'KATOA',
    no_notices: 'KĀORE HE PĀNUI I TĒNEI RĀ.',
    no_matches: 'KĀORE HE PĀNUI E TŪHONO ANA KI NGĀ TĀTARI.',
    filter_settings: 'TAUTUHINGA WHAKAATU & TĀTARI',
    click_to_configure: 'PĀTOKO HEI WHAKARITE I NGĀ TAUTUHINGA & TĀTARI',
    back_to_notices: 'HOKI KI NGĀ PĀNUI',
    motion_speed: 'NEKENEKE & TERENGA',
    speed: 'TERENGA',
    slow: 'PŪROI',
    normal: 'PŪNOKORAU',
    fast: 'TŪHITI',
    form_class: 'INGOA AKOMANGA / RŌPŪ RŪMA',
    keyword_boost: 'KUPU MATUA (TŌIA HEI WHAKARARANGI)',
    keyword_placeholder: 'TĀPIRIHIA HE KUPU MATUA KA PĒHI I TE ENTER',
    category_order: 'RĀRANGI WĀHANGA PĀNUI',
    category_order_desc: 'Tōia ngā wāhanga hei whakariterite i te raupapa whakaatu.',
    apply_sync: 'TOHUA & TŪHONO KI TE WHAKAATA',
    applied: 'KUA TOHUA & KUA TŪHONO',
    apply_changes: 'TOHUA NGĀ HURINGA',
    changes_applied: 'KUA TOHUA NGĀ HURINGA',
    close: 'KATIA',
    full_text: 'KUPUTEHI KATOA O TE PĀNUI',
    read: 'PĀNUITIA →',
    read_notice: 'PĀNUITIA TE PĀNUI',
    see: 'TIROHIA A',
    click_anywhere_close: 'PĀTOKO KI KŌNEI HEI HOKI',

    // Timetable
    current_class: 'AKOMANGA INĀIANEI',
    next_class: 'AKOMANGA WHAI AKE',
    room: 'RŪMA',
    ends: 'WHAKAMUTU',
    left: 'TOE',
    interval: 'WĀ WHAKATĀ (RECESS)',
    lunch: 'WĀ TINA (LUNCH)',
    morning_interval: 'Wā Whakatā Ata',
    lunch_break: 'Wā Tina',
    no_timetable: 'KĀORE ANŌ TE WĀTAKA KIA WHAKARITEA',
    link_kamar_prompt: 'TŪHONO TE HONONGA .ICS KAMAR HEI TŪHONO I NGĀ WĀTIKA ME TE TAIMA',
    set_up_timetable: 'WHAKARITE WĀTAKA',
    sync_timetable: 'TŪHONO WĀTAKA',
    save_timetable: 'TOHUA WĀTAKA',
    paste_ics_link: 'TĀPIRIHIA TŌ HONONGA .ICS KI KONEI',
    slideshow_step: 'KAUPEKA',
    prev: 'MUA',
    next: 'MURI',
    library_loans: 'PUKAPUKA PŪRUNGA & WHARE PUKAPUKA',
    due: 'WHAKARITEA',
    overdue: 'KUA HIPA TE WĀ',
    use_sample_link: 'WHAKAMAHIA TE HONONGA TAUIRA',
    timetable_settings: 'TAUTUHI WĀTAKA',
    back_to_timetable: 'HOKI KI TE WĀTAKA',
    periods: 'NGĀ WĀTIKA',
    schedule_view: 'TIROHANGA WĀTAKA',
    display_options: 'KŌWHIRINGA WHAKAATU',
    show_breaks: 'WHAKAATURIA NGĀ WĀ WHAKATĀ',
    highlight_current: 'MIRAMIRATIA TE WĀTIKA INĀIANEI',
    calendar_feed: 'PUNA WĀTAKA .ICS',
    reconfigure_link: 'WHAKAREREKĒ HONONGA .ICS',
    unlink_timetable: 'WETEKINA WĀTAKA',

    // Onboarding Modal
    setup_guide: 'ARATOHU WHAKARITE',
    setup_desc: 'Whakaotia tō kōtaha kia whakahohe ai i te whakauru aunoa ki te whakaata me te wātaka.',
    barcode_step: '1. TŪHONO WAEHERE PAE ĀKONGA',
    face_step: '2. TUKU MATA BIO-METRIC (HE KŌWHIRINGA)',
    timetable_step: '3. TŪHONO WĀTAKA KAMAR',
    dont_show_again: 'KAUA E WHAKAATU ANŌ',
    get_started: 'HAERE TONU',
    link_btn: 'TŪHONO',
    enroll_btn: 'TUKU',
    connect_btn: 'WHAKARITE',
    optional_tag: 'KŌWHIRINGA',

    // Settings page
    account_mgmt: 'WHAKAHAERE KŌTAHA & TŪRANGA',
    preferences_subtitle: 'TŪHONO WAEHERE PAE, MATA BIO-METRIC, REO PŪNAHA ME NGĀ TAUTUHINGA',
    authenticated: 'KUA WHAKAMANAHIA',
    student_id_title: 'TŪHONO WAEHERE PAE ĀKONGA',
    student_id_desc: 'Ko tō tau ākonga tō kī uru tūturu ki te whakaata atamai me tō tuakiri.',
    active_student_id: 'TAU WAEHERE PAE E HIKOI ANA',
    change_id: 'WHAKAREREKĒ TAU',
    unlink: 'WETEKINA',
    no_barcode_yet: 'KĀORE ANŌ TE WAEHERE PAE KIA TŪHONO',
    no_barcode_desc: 'Mā te matawai i tō kāri ākonga ka tūhono ai tō kōtaha ki te pūnaha whakaata.',
    link_barcode_btn: 'TŪHONO WAEHERE PAE ĀKONGA',
    checking: 'E TITIRO ANA...',
    face_recognition_title: 'WHAKAMŌHIO MATA BIO-METRIC (HE KŌWHIRINGA)',
    face_recognition_desc: 'Haere mai ki mua i te whakaata, ka mōhiotia tō mata me te kore e pā atu ki te karaehe.',
    face_locked_title: 'KUA RAKA TE MATA',
    face_locked_desc: 'Me tūhono tuatahi te waehere pae ākonga hei aukati i te pohehe tuakiri.',
    link_barcode_unlock: 'TŪHONO WAEHERE PAE HEI WHAREKORA',
    face_registered_title: 'KUA RĒHITA TE MATA',
    delete_rescan: 'MUKUA & TUKU ANŌ',
    ready_face_title: 'KUA RIKIRIKI TE MATA (HE KŌWHIRINGA)',
    ready_face_desc: 'Hopukina ngā whakaahua mata e 10 hei whakaako i tō tauira rorohiko.',
    register_face_btn: 'RĒHITA TE MATA',
    regional_lang_theme: 'REO PŪNAHA & KAUPAPA ATAATA',
    language_label: 'REO PŪNAHA / REO',
    theme_label: 'KAUPAPA ATAATA WHAKAATA',
    session_control: 'WHAKAHAERE WĀ MAHI',
    sign_out: 'PUTA ATU I TE KŌTAHA',
    active_tag: 'E HIKOI ANA',
    select_tag: 'KŌWHIRIA',
    drag_to_reorder: 'TŌIA HEI WHAKARARANGI',
    reset: 'WHAKATIKA ANŌ',

    // Login page
    student_portal_auth: 'WHAKAPŪMAUTANGA PŪRONGO ĀKONGA',
    sign_in_register: 'WHAKAURU / RĒHITA',
    login_terms_prefix: 'Mā te whakauru mai, ka whakaae koe ki',
    login_optional_quote: '"He kōwhiringa noa te whakamahi i te whakaata me te rēhita mai."',

    // Categories
    cat_General: 'Whānui',
    cat_Sports: 'Hākinakina',
    cat_Meetings: 'Hui',
    cat_Academic: 'Mātauranga',
    cat_Careers: 'Mahi & Umanga',
    cat_ArtsCulture: 'Toi & Ahurea',
    cat_Service: 'Ratonga',
  }
}

// Notice content translation mapping for common school notices vocabulary
const VOCAB_MAP = [
  // Facilities & Rooms
  [/\bLibrary\b/gi, 'Whare Pukapuka'],
  [/\bAuditorium\b/gi, 'Whare Hui'],
  [/\bGymnasium\b/gi, 'Whare Hākinakina'],
  [/\bGym\b/gi, 'Whare Hākinakina'],
  [/\bMain Field\b/gi, 'Papa Tākaro Matua'],
  [/\bField\b/gi, 'Papa Tākaro'],
  [/\bHall\b/gi, 'Whare Nui'],
  [/\bMusic Suite\b/gi, 'Rūma Puoro'],
  [/\bPerforming Arts Centre\b/gi, 'Whare Toi Whakaari'],
  [/\bPAC\b/gi, 'Whare Toi'],
  [/\bCourtyard\b/gi, 'Marae Atea / Marae Wātea'],
  [/\bCafeteria\b/gi, 'Whare Kai'],
  [/\bCanteen\b/gi, 'Whare Kai'],
  [/\bPool\b/gi, 'Kauanga'],
  [/\bClassroom\b/gi, 'Akomanga'],
  [/\bRoom\b/gi, 'Rūma'],
  [/\bRm\b/gi, 'Rūma'],

  // Times & Periods
  [/\bLunchtime\b/gi, 'Wā Tina'],
  [/\bLunch\b/gi, 'Tina'],
  [/\bInterval\b/gi, 'Wā Whakatā'],
  [/\bRecess\b/gi, 'Wā Whakatā'],
  [/\bMorning\b/gi, 'Ata'],
  [/\bAfternoon\b/gi, 'Ahiahi'],
  [/\bPeriod 1\b/gi, 'Wāhina 1'],
  [/\bPeriod 2\b/gi, 'Wāhina 2'],
  [/\bPeriod 3\b/gi, 'Wāhina 3'],
  [/\bPeriod 4\b/gi, 'Wāhina 4'],
  [/\bPeriod 5\b/gi, 'Wāhina 5'],
  [/\bPeriod\b/gi, 'Wāhina'],

  // Days of week
  [/\bMonday\b/gi, 'Rāhina'],
  [/\bTuesday\b/gi, 'Rātū'],
  [/\bWednesday\b/gi, 'Rāapa'],
  [/\bThursday\b/gi, 'Rāpare'],
  [/\bFriday\b/gi, 'Rāmere'],
  [/\bSaturday\b/gi, 'Rāhoroi'],
  [/\bSunday\b/gi, 'Rātapu'],
  [/\bToday\b/gi, 'I tēnei rā'],
  [/\bTomorrow\b/gi, 'Āpōpō'],

  // People & Roles
  [/\bTeacher\b/gi, 'Kaiako'],
  [/\bTeachers\b/gi, 'Ngā Kaiako'],
  [/\bStudent\b/gi, 'Ākonga'],
  [/\bStudents\b/gi, 'Ngā Ākonga'],
  [/\bPrincipal\b/gi, 'Tumuaki'],
  [/\bCoach\b/gi, 'Kaiwhakangungu'],
  [/\bDean\b/gi, 'Kaitohutohu Tau'],

  // Year levels
  [/\bYear 9\b/gi, 'Tau 9'],
  [/\bYear 10\b/gi, 'Tau 10'],
  [/\bYear 11\b/gi, 'Tau 11'],
  [/\bYear 12\b/gi, 'Tau 12'],
  [/\bYear 13\b/gi, 'Tau 13'],

  // School Activities
  [/\bMeeting\b/gi, 'Hui'],
  [/\bPractice\b/gi, 'Whakangungu'],
  [/\bRehearsal\b/gi, 'Whakaharatau'],
  [/\bAssembly\b/gi, 'Huinga Whānui'],
  [/\bAudition\b/gi, 'Whakamātautau Toi'],
  [/\bAuditions\b/gi, 'Ngā Whakamātautau Toi'],
  [/\bTryouts\b/gi, 'Whakamātautau Tīma'],
  [/\bTrial\b/gi, 'Whakamātautau'],
  [/\bTrials\b/gi, 'Ngā Whakamātautau'],
  [/\bMatch\b/gi, 'Kēmu'],
  [/\bGame\b/gi, 'Kēmu'],
  [/\bUniform\b/gi, 'Kākahu Kura'],
  [/\bHomework\b/gi, 'Mahi Kāinga'],
  [/\bCancelled\b/gi, 'Kua Whakakore'],
  [/\bPostponed\b/gi, 'Kua Nukuia'],
  [/\bImportant\b/gi, 'He Mea Nui'],
  [/\bUrgent\b/gi, 'He Hohoro Tonu'],

  // Subjects
  [/\bMathematics\b/gi, 'Pāngarau'],
  [/\bMaths\b/gi, 'Pāngarau'],
  [/\bScience\b/gi, 'Pūtaiao'],
  [/\bEnglish\b/gi, 'Ingarihi'],
  [/\bHistory\b/gi, 'Hītori'],
  [/\bGeography\b/gi, 'Mātai Matawhenua'],
  [/\bPhysics\b/gi, 'Ahupūngao'],
  [/\bChemistry\b/gi, 'Mātai Matū'],
  [/\bBiology\b/gi, 'Mātai Koiora'],
  [/\bMusic\b/gi, 'Puoro'],
  [/\bArt\b/gi, 'Toi'],
  [/\bPhysical Education\b/gi, 'Hākinakina & Koiri'],
  [/\bPE\b/gi, 'Hākinakina'],
]

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem('mirror_lang') || 'en-NZ'
  })

  const setLanguage = (lang, token) => {
    setLanguageState(lang)
    localStorage.setItem('mirror_lang', lang)
    window.dispatchEvent(new Event('languagechange'))

    // Send to server
    if (token) {
      fetch(`${API_URL}/api/users/me/language`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ language: lang }),
      }).catch(() => {})
    }
  }

  // Load language from server if user is authenticated
  const syncWithServer = async (token) => {
    if (!token) return
    try {
      const res = await fetch(`${API_URL}/api/users/me/language`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        if (data.language && data.language !== language) {
          setLanguageState(data.language)
          localStorage.setItem('mirror_lang', data.language)
        }
      }
    } catch { /* silent */ }
  }

  useEffect(() => {
    const handleStorage = () => {
      const saved = localStorage.getItem('mirror_lang') || 'en-NZ'
      if (saved !== language) setLanguageState(saved)
    }
    window.addEventListener('storage', handleStorage)
    window.addEventListener('languagechange', handleStorage)
    return () => {
      window.removeEventListener('storage', handleStorage)
      window.removeEventListener('languagechange', handleStorage)
    }
  }, [language])

  const t = (key) => {
    const dict = TRANSLATIONS[language] || TRANSLATIONS['en-NZ']
    return dict[key] || TRANSLATIONS['en-NZ'][key] || key
  }

  const translateNoticeText = (text) => {
    if (!text || language !== 'mi-NZ') return text
    let res = text
    for (const [regex, repl] of VOCAB_MAP) {
      res = res.replace(regex, repl)
    }
    return res
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, syncWithServer, t, translateNoticeText }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) {
    const lang = localStorage.getItem('mirror_lang') || 'en-NZ'
    const dict = TRANSLATIONS[lang] || TRANSLATIONS['en-NZ']
    return {
      language: lang,
      setLanguage: () => {},
      syncWithServer: () => {},
      t: (k) => dict[k] || TRANSLATIONS['en-NZ'][k] || k,
      translateNoticeText: (s) => s,
    }
  }
  return ctx
}
