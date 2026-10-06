import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

export type Lang = "en" | "ar" | "fr";

const en = {
  brand: "prof", brandSub: "your learning desk",
  nav: { today: "Today", topics: "Topics", course: "Course", sessions: "Sessions", profile: "Profile" },
  menu: "Menu", close: "Close", language: "Language", theme: "Theme", light: "Light", dark: "Dark", system: "System",
  demo: "Demo data", demoOn: "You are looking at demo data.", demoOff: "Show your own data",
  skip: "Skip to content",
  today: {
    eyebrow: "Today", title: (n: number) => (n === 0 ? "Nothing to review today" : n === 1 ? "One thing to review today" : `${n} things to review today`),
    first: "Start with", lead: "Concepts you missed or wobbled on, and the ones you knew but have not used in two weeks.",
    hint: "Ready? Run", hintAfter: "and prof starts with these.", empty: "You are up to date. Learn something new with",
    all: "All topics", last: "Last session",
  },
  status: { missed: "Missed", shaky: "Shaky", "not-checked": "Not checked", understood: "Understood", stale: "To refresh" },
  topics: { title: "Topics", lead: "How well you know each topic: the share of its concepts you understood and used recently.", mastery: "known and fresh", last: "last seen", concepts: "concepts", back: "All topics" },
  sessions: { title: "Sessions", lead: "What each session covered, newest first.", learned: "Learned", next: "Review next", did: "What you did", checks: "Comprehension checks", question: "Question", answer: "Your answer", verdict: "Verdict", weak: "Weak spots", levels: "Level", checklist: "Concepts", back: "All sessions" },
  course: { title: "Course", lead: "The modules and lessons in order, with how far each lesson is along.", minutes: "min", missing: "The course is not on this computer yet.", missingHow: "Clone nexika/courses and set LAWHA_COURSES to its folder.", level: "Level", lessons: (n: number) => `${n} ${n === 1 ? "lesson" : "lessons"}`, status: { planned: "Planned", draft: "Draft", checked: "Checked", reviewed: "Reviewed", verified: "Verified" } as Record<string, string> },
  profile: { title: "Profile", lead: "What prof knows about you, from your sessions.", empty: "prof has not written your profile yet." },
  empty: { title: "Nothing here yet", body: "prof fills this board as you learn. Start a session with", orDemo: "or look around with demo data first." },
  error: { token: "This page needs the link prof printed (it carries a one-time key). Run /prof:dashboard again.", other: "Could not load this. Is the dashboard still running?" },
  date: (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
};

type Dict = typeof en;

const ar: Dict = {
  brand: "prof", brandSub: "مكتب تعلّمك",
  nav: { today: "اليوم", topics: "المواضيع", course: "الدورة", sessions: "الجلسات", profile: "الملف" },
  menu: "القائمة", close: "إغلاق", language: "اللغة", theme: "المظهر", light: "فاتح", dark: "داكن", system: "النظام",
  demo: "بيانات تجريبية", demoOn: "أنت تتصفح بيانات تجريبية.", demoOff: "اعرض بياناتك",
  skip: "انتقل إلى المحتوى",
  today: {
    eyebrow: "اليوم", title: (n: number) => (n === 0 ? "لا شيء للمراجعة اليوم" : n === 1 ? "شيء واحد للمراجعة اليوم" : n === 2 ? "شيئان للمراجعة اليوم" : n <= 10 ? `${n} أشياء للمراجعة اليوم` : `${n} شيئاً للمراجعة اليوم`),
    first: "ابدأ بـ", lead: "مفاهيم أخطأت فيها أو ترددت، ومفاهيم عرفتها لكنك لم تستعملها منذ أسبوعين.",
    hint: "مستعد؟ شغّل", hintAfter: "وسيبدأ prof بها.", empty: "أنت على اطلاع. تعلّم شيئاً جديداً مع",
    all: "كل المواضيع", last: "آخر جلسة",
  },
  status: { missed: "أخطأت", shaky: "متردد", "not-checked": "لم يُختبر", understood: "فهمت", stale: "للتذكير" },
  topics: { title: "المواضيع", lead: "مدى معرفتك بكل موضوع: نسبة مفاهيمه التي فهمتها واستعملتها مؤخراً.", mastery: "معروف وحديث", last: "آخر مرة", concepts: "مفاهيم", back: "كل المواضيع" },
  sessions: { title: "الجلسات", lead: "ما غطّته كل جلسة، الأحدث أولاً.", learned: "تعلّمت", next: "راجع لاحقاً", did: "ما فعلته", checks: "أسئلة الفهم", question: "السؤال", answer: "إجابتك", verdict: "الحكم", weak: "نقاط الضعف", levels: "المستوى", checklist: "المفاهيم", back: "كل الجلسات" },
  course: { title: "الدورة", lead: "الوحدات والدروس بالترتيب، مع مدى تقدّم كل درس.", minutes: "دقيقة", missing: "الدورة ليست على هذا الحاسوب بعد.", missingHow: "انسخ nexika/courses واضبط LAWHA_COURSES على مجلدها.", level: "المستوى", lessons: (n: number) => (n === 1 ? "درس واحد" : n === 2 ? "درسان" : n <= 10 ? `${n} دروس` : `${n} درساً`), status: { planned: "مخطط", draft: "مسودة", checked: "مفحوص", reviewed: "مُراجع", verified: "موثّق" } },
  profile: { title: "الملف", lead: "ما يعرفه prof عنك من جلساتك.", empty: "لم يكتب prof ملفك بعد." },
  empty: { title: "لا شيء هنا بعد", body: "يملأ prof هذه اللوحة كلما تعلّمت. ابدأ جلسة بـ", orDemo: "أو تجوّل أولاً في البيانات التجريبية." },
  error: { token: "تحتاج هذه الصفحة إلى الرابط الذي طبعه prof (فيه مفتاح لمرة واحدة). شغّل /prof:dashboard من جديد.", other: "تعذّر التحميل. هل ما زالت اللوحة تعمل؟" },
  date: (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("ar", { day: "numeric", month: "long", year: "numeric", numberingSystem: "latn" }),
};

const fr: Dict = {
  brand: "prof", brandSub: "votre bureau d'étude",
  nav: { today: "Aujourd'hui", topics: "Sujets", course: "Cours", sessions: "Séances", profile: "Profil" },
  menu: "Menu", close: "Fermer", language: "Langue", theme: "Thème", light: "Clair", dark: "Sombre", system: "Système",
  demo: "Données de démo", demoOn: "Vous consultez des données de démonstration.", demoOff: "Voir vos données",
  skip: "Aller au contenu",
  today: {
    eyebrow: "Aujourd'hui", title: (n: number) => (n === 0 ? "Rien à revoir aujourd'hui" : n === 1 ? "Une chose à revoir aujourd'hui" : `${n} choses à revoir aujourd'hui`),
    first: "Commencez par", lead: "Les notions manquées ou hésitantes, et celles que vous saviez mais n'avez pas utilisées depuis deux semaines.",
    hint: "Prêt ? Lancez", hintAfter: "et prof commence par celles-ci.", empty: "Vous êtes à jour. Apprenez quelque chose de nouveau avec",
    all: "Tous les sujets", last: "Dernière séance",
  },
  status: { missed: "Manqué", shaky: "Hésitant", "not-checked": "Non vérifié", understood: "Compris", stale: "À rafraîchir" },
  topics: { title: "Sujets", lead: "Votre maîtrise de chaque sujet : la part de ses notions comprises et utilisées récemment.", mastery: "su et récent", last: "vu le", concepts: "notions", back: "Tous les sujets" },
  sessions: { title: "Séances", lead: "Ce que chaque séance a couvert, la plus récente en premier.", learned: "Appris", next: "À revoir", did: "Ce que vous avez fait", checks: "Questions de compréhension", question: "Question", answer: "Votre réponse", verdict: "Verdict", weak: "Points faibles", levels: "Niveau", checklist: "Notions", back: "Toutes les séances" },
  course: { title: "Cours", lead: "Les modules et leçons dans l'ordre, avec l'avancement de chaque leçon.", minutes: "min", missing: "Le cours n'est pas encore sur cet ordinateur.", missingHow: "Clonez nexika/courses et réglez LAWHA_COURSES sur son dossier.", level: "Niveau", lessons: (n: number) => `${n} ${n === 1 ? "leçon" : "leçons"}`, status: { planned: "Prévu", draft: "Brouillon", checked: "Vérifié", reviewed: "Relu", verified: "Validé" } },
  profile: { title: "Profil", lead: "Ce que prof sait de vous, d'après vos séances.", empty: "prof n'a pas encore écrit votre profil." },
  empty: { title: "Rien ici pour l'instant", body: "prof remplit ce tableau à mesure que vous apprenez. Commencez une séance avec", orDemo: "ou explorez d'abord les données de démo." },
  error: { token: "Cette page a besoin du lien affiché par prof (il porte une clé à usage unique). Relancez /prof:dashboard.", other: "Chargement impossible. Le tableau de bord tourne-t-il encore ?" },
  date: (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }),
};

const DICTS: Record<Lang, Dict> = { en, ar, fr };

export function initialLang(): Lang {
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (fromUrl === "en" || fromUrl === "ar" || fromUrl === "fr") return fromUrl;
  try {
    const saved = localStorage.getItem("prof-lang");
    if (saved === "en" || saved === "ar" || saved === "fr") return saved;
  } catch { /* ignore */ }
  const nav = navigator.language.slice(0, 2);
  return nav === "ar" || nav === "fr" ? nav : "en";
}

const Ctx = createContext<{ lang: Lang; t: Dict; setLang: (l: Lang) => void }>({ lang: "en", t: en, setLang: () => undefined });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  const value = useMemo(() => ({
    lang, t: DICTS[lang],
    setLang: (l: Lang) => {
      try { localStorage.setItem("prof-lang", l); } catch { /* ignore */ }
      setLangState(l);
    },
  }), [lang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useT = () => useContext(Ctx);

/** A course title in the current language, falling back to English, then to the id. */
export function pick(title: Partial<Record<Lang, string>>, lang: Lang, fallback: string): string {
  return title[lang] ?? title.en ?? fallback;
}
