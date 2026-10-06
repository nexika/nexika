export type Lang = "en" | "ar";

export interface Copy {
  nav: { features: string; how: string; pricing: string; start: string; switchLabel: string; switchTo: string; themeLight: string; themeDark: string };
  hero: { line: string; echo: string; sub: string; primary: string; secondary: string; free: string };
  sheet: {
    label: string;
    title: string;
    saved: string;
    words: string;
    ltr: string;
    rtl: string;
    paragraphs: { text: string; dir: "ltr" | "rtl"; lang: Lang }[];
  };
  features: { heading: string; items: { title: string; body: string }[] };
  how: { heading: string; steps: { title: string; body: string }[] };
  quote: { original: string; translation?: string; translatedNote?: string; name: string; role: string };
  pricing: {
    heading: string;
    sub: string;
    free: { name: string; price: string; per: string; for: string; items: string[]; cta: string };
    pro: { name: string; price: string; per: string; for: string; items: string[]; cta: string; note: string };
  };
  cta: { heading: string; body: string; button: string };
  footer: { made: string; privacy: string; terms: string; contact: string };
}

const pEn = {
  text: "The first house I remember had a fig tree by the door. My grandmother called it the patient one.",
  dir: "ltr" as const,
  lang: "en" as const,
};
const pAr = {
  text: "كانت جدتي تقول إن التينة لا تستعجل، وإن الكتابة مثلها: سطر اليوم، وسطر غدًا.",
  dir: "rtl" as const,
  lang: "ar" as const,
};

const quoteAr =
  "أكتب أطروحتي بالعربية وملاحظاتي بالإنجليزية. قلم هو أول محرّر توقفت فيه عن مطاردة المؤشّر من طرف السطر إلى طرفه الآخر.";

export const copy: Record<Lang, Copy> = {
  en: {
    nav: {
      features: "Features",
      how: "How it works",
      pricing: "Pricing",
      start: "Start writing",
      switchLabel: "اقرأ هذه الصفحة بالعربية",
      switchTo: "العربية",
      themeLight: "Switch to light theme",
      themeDark: "Switch to dark theme",
    },
    hero: {
      line: "Write in Arabic and English, on one calm page.",
      echo: "اكتب بالعربية والإنجليزية، في صفحة واحدة هادئة.",
      sub: "Qalam is a writing app for notes, drafts and long essays. The editor is the same quiet page in both languages, so you can think in one and quote in the other.",
      primary: "Start writing free",
      secondary: "See pricing",
      free: "Free for notes and drafts. No card needed.",
    },
    sheet: {
      label: "A Qalam document being written in English, then in Arabic",
      title: "On leaving home",
      saved: "Saved",
      words: "words",
      ltr: "Left to right",
      rtl: "Right to left",
      paragraphs: [pEn, pAr],
    },
    features: {
      heading: "Made for writing that crosses languages",
      items: [
        {
          title: "Every paragraph finds its own direction",
          body: "Type in Arabic and the line runs right to left. Switch to English and the next paragraph turns around. There is no setting to change and no button to press.",
        },
        {
          title: "Notes, drafts and essays in one place",
          body: "Start with a quick note in a lecture, grow it into a draft, and finish it as an essay with headings, footnotes and an outline you can rearrange.",
        },
        {
          title: "Arabic set like a book, not a form",
          body: "Naskh and Latin type chosen to sit together at the same size, room between lines for diacritics, and Arabic or Western digits, whichever you prefer.",
        },
      ],
    },
    how: {
      heading: "How it works",
      steps: [
        { title: "Open a page", body: "Use Qalam in your browser or on your phone. Your notes sync between them." },
        { title: "Write in either language", body: "Or both. Qalam sets the direction of each paragraph as you type, and keeps punctuation where it belongs." },
        { title: "Share what you wrote", body: "Send a PDF to your teacher, a Word file to your editor, or a read-only link to anyone." },
      ],
    },
    quote: {
      original: quoteAr,
      translation:
        "I write my thesis in Arabic and my notes in English. Qalam is the first editor where I stopped chasing the cursor from one end of the line to the other.",
      translatedNote: "Translated from Arabic",
      name: "Nour Haddad",
      role: "Master’s student in comparative literature, Beirut",
    },
    pricing: {
      heading: "Pricing",
      sub: "Start free. Move to Pro when your writing gets long.",
      free: {
        name: "Free",
        price: "$0",
        per: "for as long as you like",
        for: "For notes and everyday drafts.",
        items: ["Unlimited notes and drafts", "Arabic and English in every document", "Sync on two devices", "Export to PDF"],
        cta: "Start writing free",
      },
      pro: {
        name: "Pro",
        price: "$5",
        per: "a month, or $48 a year",
        for: "For theses, books and long essays.",
        items: [
          "Everything in Free",
          "Outlines, footnotes and citations",
          "Full version history",
          "Sync on every device",
          "Export to Word, EPUB and Markdown",
        ],
        cta: "Get Pro",
        note: "Students pay half with a university email.",
      },
    },
    cta: {
      heading: "The page is ready in both languages.",
      body: "Open Qalam and write the first line of whatever you are working on.",
      button: "Start writing free",
    },
    footer: { made: "Qalam. A calm editor for Arabic and English.", privacy: "Privacy", terms: "Terms", contact: "Contact" },
  },
  ar: {
    nav: {
      features: "المزايا",
      how: "طريقة العمل",
      pricing: "الأسعار",
      start: "ابدأ الكتابة",
      switchLabel: "Read this page in English",
      switchTo: "English",
      themeLight: "التبديل إلى الوضع الفاتح",
      themeDark: "التبديل إلى الوضع الداكن",
    },
    hero: {
      line: "اكتب بالعربية والإنجليزية، في صفحة واحدة هادئة.",
      echo: "Write in Arabic and English, on one calm page.",
      sub: "قلم تطبيق كتابة للملاحظات والمسودات والمقالات الطويلة. المحرّر صفحة هادئة واحدة في اللغتين، فتفكّر بلغة وتقتبس من الأخرى.",
      primary: "ابدأ الكتابة مجانًا",
      secondary: "اطّلع على الأسعار",
      free: "مجاني للملاحظات والمسودات، دون بطاقة دفع.",
    },
    sheet: {
      label: "مستند في قلم يُكتب بالعربية ثم بالإنجليزية",
      title: "عن مغادرة البيت",
      saved: "محفوظ",
      words: "كلمة",
      ltr: "من اليسار إلى اليمين",
      rtl: "من اليمين إلى اليسار",
      paragraphs: [pAr, pEn],
    },
    features: {
      heading: "صُمّم لكتابة تعبر بين لغتين",
      items: [
        {
          title: "كل فقرة تعرف اتجاهها",
          body: "اكتب بالعربية فيمضي السطر من اليمين إلى اليسار، وانتقل إلى الإنجليزية فتنعطف الفقرة التالية. لا إعداد تغيّره ولا زر تضغطه.",
        },
        {
          title: "الملاحظات والمسودات والمقالات في مكان واحد",
          body: "ابدأ بملاحظة سريعة في المحاضرة، ثم حوّلها إلى مسودة، وأنهِها مقالةً بعناوين وحواشٍ ومخطط تعيد ترتيبه كما تشاء.",
        },
        {
          title: "العربية مصفوفة كما في الكتب",
          body: "خط نسخ وخط لاتيني اختيرا ليتجاورا بالحجم نفسه، ومسافة بين الأسطر تتسع للتشكيل، وأرقام عربية أو غربية بحسب ما تفضّل.",
        },
      ],
    },
    how: {
      heading: "طريقة العمل",
      steps: [
        { title: "افتح صفحة", body: "استخدم قلم في المتصفح أو على هاتفك، وتبقى ملاحظاتك متزامنة بينهما." },
        { title: "اكتب بأي لغة", body: "أو باللغتين معًا. يضبط قلم اتجاه كل فقرة أثناء الكتابة، ويبقي علامات الترقيم في مكانها." },
        { title: "شارك ما كتبت", body: "أرسل ملف PDF إلى أستاذك، أو ملف Word إلى محرّرك، أو رابط قراءة إلى من تشاء." },
      ],
    },
    quote: {
      original: quoteAr,
      name: "نور حداد",
      role: "طالبة ماجستير في الأدب المقارن، بيروت",
    },
    pricing: {
      heading: "الأسعار",
      sub: "ابدأ مجانًا، وانتقل إلى النسخة الاحترافية حين تطول كتابتك.",
      free: {
        name: "المجانية",
        price: "مجانًا",
        per: "ما دمت تريد",
        for: "للملاحظات والمسودات اليومية.",
        items: ["ملاحظات ومسودات بلا حدود", "العربية والإنجليزية في كل مستند", "مزامنة على جهازين", "تصدير إلى PDF"],
        cta: "ابدأ الكتابة مجانًا",
      },
      pro: {
        name: "الاحترافية",
        price: "٥ $",
        per: "شهريًا، أو ٤٨ $ سنويًا",
        for: "للأطروحات والكتب والمقالات الطويلة.",
        items: [
          "كل ما في المجانية",
          "مخططات وحواشٍ ومراجع",
          "سجل كامل للنسخ",
          "مزامنة على كل أجهزتك",
          "تصدير إلى Word وEPUB وMarkdown",
        ],
        cta: "اشترك في الاحترافية",
        note: "يدفع الطلاب النصف عند التسجيل ببريد جامعي.",
      },
    },
    cta: {
      heading: "الصفحة جاهزة باللغتين.",
      body: "افتح قلم واكتب السطر الأول مما تعمل عليه.",
      button: "ابدأ الكتابة مجانًا",
    },
    footer: { made: "قلم. محرّر هادئ للعربية والإنجليزية.", privacy: "الخصوصية", terms: "الشروط", contact: "تواصل معنا" },
  },
};
