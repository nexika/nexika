import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "@fontsource/source-sans-3/400.css";
import "@fontsource/source-sans-3/400-italic.css";
import "@fontsource/source-sans-3/600.css";
import "./styles.css";
import { createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { MotionConfig } from "motion/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider, initialLang } from "./i18n";
import { initialTheme, Layout } from "./layout";
import "./lib";
import { Course } from "./screens/course";
import { Profile } from "./screens/profile";
import { SessionPage, Sessions } from "./screens/sessions";
import { Today } from "./screens/today";
import { TopicPage, Topics } from "./screens/topics";

// Set the theme, language and direction before the first paint: a dark-mode reader never sees a
// white flash, and an Arabic page never draws left to right first and then flips.
{
  const lang = initialLang();
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  const theme = initialTheme();
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

const root = createRootRoute({ component: Layout });
const routes = [
  createRoute({ getParentRoute: () => root, path: "/", component: Today }),
  createRoute({ getParentRoute: () => root, path: "/topics", component: Topics }),
  createRoute({ getParentRoute: () => root, path: "/topics/$slug", component: TopicPage }),
  createRoute({ getParentRoute: () => root, path: "/sessions", component: Sessions }),
  createRoute({ getParentRoute: () => root, path: "/sessions/$id", component: SessionPage }),
  createRoute({ getParentRoute: () => root, path: "/course", component: Course }),
  createRoute({ getParentRoute: () => root, path: "/profile", component: Profile }),
];
const router = createRouter({ routeTree: root.addChildren(routes), defaultPreload: false });

declare module "@tanstack/react-router" {
  interface Register { router: typeof router }
}

// The fonts come from this same local server: wait for them (at most 800ms) before the first paint,
// so text does not rewrap and push the page down when they arrive.
const arabic = document.documentElement.lang === "ar";
// Each font is asked for text in its own script: a Latin font asked for Arabic letters loads nothing.
// Arabic pages need both (the brand, EN/FR and the learner's English notes are Latin).
const fonts: [string, string][] = [['400 1em "Source Sans 3"', "Ab"], ['600 1em "Source Sans 3"', "Ab"], ['600 1em "Fraunces"', "Ab"], ...(arabic ? [['400 1em "IBM Plex Sans Arabic"', "ابت"], ['600 1em "IBM Plex Sans Arabic"', "ابت"]] as [string, string][] : [])];
await Promise.race([Promise.all(fonts.map(([font, text]) => document.fonts.load(font, text))), new Promise((r) => setTimeout(r, 800))]).catch(() => undefined);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <I18nProvider>
        <RouterProvider router={router} />
      </I18nProvider>
    </MotionConfig>
  </StrictMode>,
);
