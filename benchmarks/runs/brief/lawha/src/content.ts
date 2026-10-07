export type Lang = "en" | "ar";

export function currentLang(): Lang {
  if (typeof document === "undefined") return "en";
  return document.documentElement.lang === "ar" ? "ar" : "en";
}

const en = {
  skip: "Skip to content",
  nav: { features: "Features", how: "How it works", pricing: "Pricing" },
  switchLang: { label: "العربية", href: "?lang=ar", hreflang: "ar", aria: "اقرأ هذه الصفحة بالعربية" },
  theme: { toDark: "Switch to dark theme", toLight: "Switch to light theme" },
  start: "Start writing",
  hero: {
    kicker: "A writing app for Arabic and English",
    title: "Write in two languages.",
    titleEnd: "Think on one calm page.",
    other: { lang: "ar" as Lang, text: "اكتب بلغتين، وفكّر في صفحة واحدة هادئة." },
    sub: "Qalam is one quiet editor for notes, drafts and long essays. Every paragraph finds its own direction, so you never fight the cursor again.",
    secondary: "See how it works",
    note: "Free for students. No card needed.",
  },
  editor: {
    file: "essay-draft.qalam",
    saved: "Saved",
    heading: "On translating silence",
    p1: "Some words refuse to travel. My grandmother said",
    p1q: "صبرٌ جميل",
    p1end: "and meant a whole season of waiting.",
    p2: "الترجمة ليست نقلاً للكلمات، بل إصغاءٌ لما بينها.",
    count: "412 words · 2 min read",
  },
  features: {
    eyebrow: "What it does",
    title: "One editor, both directions",
    other: { lang: "ar" as Lang, text: "محرر واحد، باتجاهين" },
    items: [
      { n: "01", title: "Direction, per paragraph", body: "Type Arabic and the line turns right to left; switch to English and it turns back. Punctuation, numbers and quotes stay where they belong." },
      { n: "02", title: "From note to essay", body: "Start with a two-line note. Grow it into a draft, then an essay with headings and footnotes, without moving it to another app." },
      { n: "03", title: "Quiet by design", body: "No toolbar shouting at you. A focus mode that dims everything but your sentence, and word counts in either numeral system." },
    ],
  },
  how: {
    eyebrow: "How it works",
    title: "Three steps, no setup",
    other: { lang: "ar" as Lang, text: "ثلاث خطوات، بلا إعداد" },
    steps: [
      { title: "Open a page", body: "Every note starts as a blank, calm page. Give it a title or don't." },
      { title: "Write in either language", body: "Mix Arabic and English freely. Qalam sets each paragraph's direction and font for you." },
      { title: "Shape it and share it", body: "Turn notes into sections, export to PDF or Word, or share a read-only link with your tutor." },
    ],
  },
  quote: {
    text: "I wrote my whole thesis in Qalam, half in Arabic, half in English. It is the first editor that never made me feel like my second language was a guest.",
    name: "Layla Haddad",
    role: "MA student in comparative literature",
  },
  pricing: {
    eyebrow: "Pricing",
    title: "Free to write. Pro when you need more.",
    other: { lang: "ar" as Lang, text: "الكتابة مجانية، والاحترافي حين تحتاج المزيد." },
    period: "/ month",
    plans: [
      { name: "Free", price: "$0", blurb: "For notes and coursework.", items: ["Unlimited notes and drafts", "Arabic and English, mixed freely", "Focus mode", "Sync on two devices"], cta: "Start free", featured: false },
      { name: "Pro", price: "$6", blurb: "For theses, books and long essays.", items: ["Everything in Free", "Footnotes, outlines and versions", "Export to PDF, Word and Markdown", "Sync on every device", "Share read-only links"], cta: "Try Pro free for 14 days", featured: true },
    ],
    badge: "Most writers",
  },
  cta: {
    title: "Your next essay is waiting for a calm page.",
    other: { lang: "ar" as Lang, text: "مقالك القادم ينتظر صفحة هادئة." },
    button: "Start writing, free",
  },
  footer: { made: "Qalam. Made for people who write in more than one language.", rights: "© 2026 Qalam" },
};

export type Content = typeof en;

const ar: Content = {
  skip: "انتقل إلى المحتوى",
  nav: { features: "المزايا", how: "كيف يعمل", pricing: "الأسعار" },
  switchLang: { label: "English", href: "?", hreflang: "en", aria: "Read this page in English" },
  theme: { toDark: "التبديل إلى المظهر الداكن", toLight: "التبديل إلى المظهر الفاتح" },
  start: "ابدأ الكتابة",
  hero: {
    kicker: "تطبيق كتابة للعربية والإنجليزية",
    title: "اكتب بلغتين،",
    titleEnd: "وفكّر في صفحة واحدة هادئة.",
    other: { lang: "en", text: "Write in two languages. Think on one calm page." },
    sub: "قلم محررٌ هادئ واحد للملاحظات والمسودات والمقالات الطويلة. كل فقرة تجد اتجاهها وحدها، فلا تتصارع مع المؤشر بعد اليوم.",
    secondary: "شاهد كيف يعمل",
    note: "مجاني للطلاب، دون بطاقة دفع.",
  },
  editor: {
    file: "مسودة-مقال.qalam",
    saved: "محفوظ",
    heading: "عن ترجمة الصمت",
    p1: "بعض الكلمات ترفض السفر. قالت جدتي",
    p1q: "صبرٌ جميل",
    p1end: "وكانت تعني موسماً كاملاً من الانتظار.",
    p2: "Translation is not moving words; it is listening to what lies between them.",
    count: "٤١٢ كلمة · دقيقتان للقراءة",
  },
  features: {
    eyebrow: "ماذا يفعل",
    title: "محرر واحد، باتجاهين",
    other: { lang: "en", text: "One editor, both directions" },
    items: [
      { n: "٠١", title: "اتجاه لكل فقرة", body: "اكتب بالعربية فيتجه السطر من اليمين إلى اليسار، وانتقل إلى الإنجليزية فيعود. وتبقى علامات الترقيم والأرقام والاقتباسات في مكانها." },
      { n: "٠٢", title: "من ملاحظة إلى مقال", body: "ابدأ بملاحظة من سطرين، ثم حوّلها إلى مسودة، ثم إلى مقال بعناوين وحواشٍ، دون أن تنقلها إلى تطبيق آخر." },
      { n: "٠٣", title: "هادئ بطبيعته", body: "لا شريط أدوات يصرخ في وجهك. وضع تركيز يُخفت كل شيء إلا جملتك، وعدّاد كلمات بالأرقام التي تفضّلها." },
    ],
  },
  how: {
    eyebrow: "كيف يعمل",
    title: "ثلاث خطوات، بلا إعداد",
    other: { lang: "en", text: "Three steps, no setup" },
    steps: [
      { title: "افتح صفحة", body: "كل ملاحظة تبدأ صفحةً بيضاء هادئة. أعطها عنواناً أو اتركها بلا عنوان." },
      { title: "اكتب بأي لغة", body: "امزج العربية والإنجليزية بحرية، وقلم يضبط اتجاه كل فقرة وخطّها نيابةً عنك." },
      { title: "رتّبها وشاركها", body: "حوّل الملاحظات إلى أقسام، وصدّرها إلى PDF أو Word، أو شارك رابط قراءة مع مشرفك." },
    ],
  },
  quote: {
    text: "كتبتُ أطروحتي كلها في قلم، نصفها بالعربية ونصفها بالإنجليزية. إنه أول محرر لم يُشعرني بأن لغتي الثانية ضيفة.",
    name: "ليلى حداد",
    role: "طالبة ماجستير في الأدب المقارن",
  },
  pricing: {
    eyebrow: "الأسعار",
    title: "الكتابة مجانية. والاحترافي حين تحتاج المزيد.",
    other: { lang: "en", text: "Free to write. Pro when you need more." },
    period: "/ شهرياً",
    plans: [
      { name: "مجاني", price: "٠ $", blurb: "للملاحظات والواجبات.", items: ["ملاحظات ومسودات بلا حدود", "العربية والإنجليزية معاً", "وضع التركيز", "مزامنة على جهازين"], cta: "ابدأ مجاناً", featured: false },
      { name: "احترافي", price: "٦ $", blurb: "للأطروحات والكتب والمقالات الطويلة.", items: ["كل ما في المجاني", "حواشٍ ومخططات ونسخ سابقة", "تصدير إلى PDF وWord وMarkdown", "مزامنة على كل أجهزتك", "روابط قراءة للمشاركة"], cta: "جرّب الاحترافي مجاناً ١٤ يوماً", featured: true },
    ],
    badge: "اختيار معظم الكتّاب",
  },
  cta: {
    title: "مقالك القادم ينتظر صفحة هادئة.",
    other: { lang: "en", text: "Your next essay is waiting for a calm page." },
    button: "ابدأ الكتابة مجاناً",
  },
  footer: { made: "قلم. صُنع لمن يكتب بأكثر من لغة.", rights: "© ٢٠٢٦ قلم" },
};

export const content: Record<Lang, Content> = { en, ar };
