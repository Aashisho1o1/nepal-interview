# Design review handoff: Nepal student interview practice (web frontend)

**For:** an AI design reviewer (you), asked for detailed, opinionated feedback on the visual design, layout, copy and flow of a web app.
**From:** the product owner (Aashish). **Date:** 2 November 2026.
**Attached with this document:** screenshots from `docs/design-review/screenshots/` (listed in section 6). If you can read code, the owner may also attach `apps/web/app/page.tsx` and `apps/web/app/globals.css`.

---

## 0. What I'm asking you to do

Review the frontend of our product and tell us how to make it **clean, elegant, beautiful and immediately clear about what we offer**. We want it to feel **super clean and neat**: calm, trustworthy, friendly, and obvious within five seconds.

Please read sections 1–5 for context, look at every screenshot, then answer using the **response format in section 9**. Be specific: name the screen and the element, say what is wrong and why, and give a concrete fix (layout, sizes, colours, copy). Generic advice ("improve hierarchy", "add whitespace") isn't useful unless it says exactly where and how.

Do **not** propose anything that breaks the constraints in section 7. They are legal, trust and technical rules, not taste.

---

## 1. The product in one paragraph

A website where **students from Nepal practise their UK university pre-CAS interview** (the credibility interview a university holds before issuing the CAS needed for the visa) with a **fictional AI interviewer**, by **voice** or **video**, and then get **feedback built on their own words and their own documents**. Before practising, the student checks the key facts we extracted from their documents (university, course, costs, funds, sponsor) and confirms what's right or rejects what's wrong. The interviewer only uses confirmed facts. After the session the student sees what went well, what to practise next, and the transcript, then rates the experience.

**It is practice only.** It is not a government service, the interviewer is not a real officer, and nothing predicts a visa decision.

## 2. Who uses it and what they need

| | |
|---|---|
| **Primary user** | Nepali students, mostly 18–28, holding an offer from a UK university and preparing for its pre-CAS credibility interview. |
| **Their state of mind** | Nervous. A visa refusal is expensive and emotional. They want to feel prepared and less afraid. |
| **English** | Good reading English, but not native. Plain words and short sentences matter. |
| **Devices and network** | **Mostly phones** (Android Chrome, some iPhone Safari), often on **mobile data** in Nepal. Low bandwidth, sometimes noisy rooms. Desktop is secondary. |
| **How they arrive** | Often through an education **consultancy** that gives them an account (no public sign-up yet). Early test group: 5–10 students. |
| **Secondary users** | Consultancy counsellors (will review some feedback); an admin who manages credits (admin page not built yet, out of scope here). |

**What a student must understand in five seconds on the home page:**
1. This helps me practise my pre-CAS (university credibility) interview.
2. I talk to an AI interviewer, by voice or video.
3. It uses my real details and gives me useful feedback.
4. It's safe and honest (practice only, not the government).
5. How to start.

## 3. Product goals for this phase

1. **Students start a practice session within a minute** of arriving, on a phone.
2. **Two tiers to compare:**
   - **Voice only** (cheaper, phone-friendly): ElevenLabs voice agent. 5 minutes, 3 questions.
   - **Video interviewer** (premium): a talking avatar from HeyGen LiveAvatar, driven by the same voice agent. One brain, two faces.
3. **Feedback students trust:** quotes their exact words, links each point to the transcript, never judges honesty or emotion.
4. **Learn which tier students prefer:** a short rating after every session (realism, reply speed, audio/video OK, would use again).
5. **Feel premium enough that a family would pay for it**, while staying light and fast on mobile data.

## 4. Features and screens (current state)

The app has six screens. Each is listed with its purpose, what's on it today, and its states.

### 4.1 Home `/` (screenshots 01, 02, 07)
**Purpose:** welcome, explain the service, let the student pick voice or video, then sign in.
**Order today:**
1. **Top bar:** small logo mark (sun over a red mountain in a peach circle) plus the name "Interview Practice"; a "Sign in" pill on the right (or "Hi, Asha" when signed in).
2. **Hero:**
   - pill "Namaste, and welcome!";
   - headline "Walk into your pre-CAS interview **feeling ready**." ("feeling ready" has a yellow highlighter underline);
   - lead paragraph;
   - two buttons, "Start practising" (filled) and "How it works" (outline);
   - three ticks: "Uses only facts you confirm", "Short sessions", "Video or voice".

   On the right sits an illustration card: sky gradient, sun, blue mountains, green hills. Over it are a white chat bubble ("Interviewer: Why did you choose this university?"), a coral bubble with the student's answer, and a green pill "✓ Clear and specific!".
3. **"Why students like it":** four feature cards with tinted icons:
   - Built from your documents;
   - Short, focused sessions;
   - Feedback in your own words;
   - Your funding, made clear.
4. **"How it works":** four numbered steps (yellow number circles): Pick your interviewer → Check your facts → Have a conversation → See your scorecard.
5. **"Who would you like to talk to?"** (or "Welcome back, Asha! …" when signed in): two large cards, each with an illustration, title, description, tags and a "Practise with … →" line.
   - **Video interviewer:** a smiley face on a screen; "Best on Wi-Fi".
   - **Voice only:** a mic with sound bars; "Works on mobile data".

   When signed in, the cards also show minutes left.
6. **Sign-in card** (only when signed out): "Sign in to start". After a card is picked it shows a chip "You picked: Voice only · change". Below are email, password, a full-width button and "Accounts are set up for you during this early preview."
7. Fine print ("Your interviewer is a fictional AI, not a consular officer.") and a footer disclaimer.

**Behaviour:** picking a card when signed out scrolls to the sign-in card and focuses email. After sign-in, the student goes to Facts if they haven't confirmed them, otherwise to the Interview screen with their pick preselected.

### 4.2 Confirm your facts `/prepare` (screenshot 03)
**Purpose:** the student checks each fact we extracted from their documents and confirms or rejects it. This is the core trust feature: "what's right / what's wrong in my documents".
**Today, from the top:**
- **Title and instructions.**
- **"Facts from your documents" card:** about 13 rows. Each row shows the raw field key (e.g. `funding.costs`), the value in bold, "Source: document name — 'quoted snippet'", and a status pill (proposed / confirmed / rejected). Proposed facts show **Confirm** and **Reject** buttons.
- **Save button:** "Save confirmed facts" / "Save a new version".
- **"Funding arithmetic" table:** first-year costs, scholarships subtracted, amount to fund, funds in confirmed facts, and the gap, with a caveat paragraph and "Be ready to explain:" bullets.
- **"Continue to practice" button.**

### 4.3 Interview picker `/interview`, before starting (screenshot 04)
- **Title:** "Your pre-CAS practice interview", with a disclaimer paragraph.
- **Interviewers:** a radio list, "Video interviewer A" and "Voice only". Each has a dense note covering data use, which vendor gets the voice (required for consent), minutes left and "No scorecard for this one yet".
- **Button:** "Start practice". Most of the desktop screen is empty.

### 4.4 Live interview, same page (screenshot 05)
- **Voice:** a peach panel with a large orb (coral and pulsing while the interviewer speaks, blue while listening). Overlay chips show "Fictional AI interviewer · practice" (top left, dark translucent) and a countdown (top right).
  - Under the panel: a status line ("Interviewer speaking"), the format disclaimer and a full-width dark-red "End session" button.
- **Video:** HeyGen's player inside a 16:9 frame with the same chips and button. No screenshot, because each video session spends paid credits.
- **States:** reserving, connecting, tap-to-start (video), listening, thinking, speaking, interrupted, reconnecting, ended, and errors such as microphone blocked or connection failed (time refunded).

### 4.5 Results and feedback `/sessions/[id]` (screenshots 06, 08)
- **Header:** title "Practice feedback" and a disclaimer.
- **Status card:** raw status pills (e.g. "completed", "deadline") and "Used: 0:00 video, 2:30 voice."
- **If a transcript exists:**
  - **"What we observed":** findings, each with a coloured left border (green = strength, yellow = practise this, red = document mismatch). Each finding has a category, a severity pill, the student's exact quote (underlined link to the transcript line), a timestamp, an explanation, "**Next:** …" and "Based on: (internal fact ids)".
  - **Then:** "Practise next" bullets, "Not yet confirmed" bullets and the full **Transcript** (speaker, timestamp, text).
- **If no transcript** (static video embed; voice until its transcript connection is built): a sentence explaining there's no scorecard.
- **Rating form:** realism 1–5, reply speed (4 options), "Could you clearly hear (and see)…" yes/no, "Would you practise again" yes/no, an optional comment and "Submit rating".
- **Footer links:** "Practise again · Your facts".

### 4.6 Not built yet (design suggestions welcome, briefly)
- Admin page
- Public sign-up
- Pricing or credit purchase
- Nepali-language version
- A "my sessions" history page

## 5. Current visual system

All styling is hand-written CSS in one file (`apps/web/app/globals.css`) with CSS variables. There is no Tailwind and no component library. The font is **Nunito** (rounded sans), loaded through `next/font`. There is one light theme only (the owner found the old dark mode "too dark").

| Token | Value | Used for |
|---|---|---|
| `--bg` | `#fffaf3` warm cream | page background |
| `--surface` | `#ffffff` | cards |
| `--ink` | `#1f2430` | text |
| `--muted` | `#5b6272` | secondary text |
| `--line` | `#efe5d7` | borders |
| `--accent` | `#cf3f25` coral-red (hover `#b0331b`, soft `#ffede5`) | primary buttons, links, kicker labels, selected state |
| `--sky` | `#2f6fde` (soft `#e8f1ff`) | voice illustration, focus ring |
| `--sun` | `#ffc94d` (soft `#fff5d9`) | highlighter, step numbers |
| `--good` | `#1d7f5b` (soft `#e3f5ec`) | ticks, "confirmed", strengths |
| `--warn` / `--bad` | `#975600` / `#bf3329` | warnings / errors and the End button |
| Radius | 18px cards, 24–28px large cards, pills fully rounded | |
| Shadow | soft two-layer shadow on cards | |

**Type scale:**
- body: 16px, line-height 1.55;
- home hero: `clamp(2.2rem, 5.4vw, 3.6rem)`, weight 800;
- section titles: `clamp(1.6rem, 3.4vw, 2.3rem)`;
- inner-page h1: 1.75rem; h2: 1.15rem.

**Layout:**
- home sections: max width 1080px;
- inner pages: a single 760px column;
- buttons: 48–52px tall pills;
- phone: 16–20px side margins, no sideways scrolling at 390px.

## 6. Screenshots (attach these)

Phone screenshots are at 390px width (2× pixels). Long phone pages are split into numbered parts, top to bottom.

| File | Screen |
|---|---|
| `01-home-desktop.png`, `01-home-phone-part1…7.png` | Home, signed out, full page |
| `02-home-signin-picked-desktop.png`, `02-home-signin-picked-phone.png` | Sign-in card after picking "Voice only" |
| `07-home-signed-in-choose-desktop.png`, `07-home-signed-in-choose-phone-part1…2.png` | "Welcome back" + interviewer choice with minutes left |
| `03-facts-and-funding-desktop.png`, `03-facts-and-funding-phone-part1…4.png` | Confirm your facts + funding table |
| `04-interview-picker-desktop.png`, `04-interview-picker-phone.png` | Interview picker before starting |
| `05-voice-interview-live-phone.png` | Live voice interview (phone) |
| `06-scorecard-desktop.png`, `06-scorecard-phone-part1…4.png` | Feedback page with findings, transcript and rating (sample transcript) |
| `08-results-no-transcript-phone.png` | Results when the interviewer gives no transcript (rating only) |

All data shown is synthetic ("Asha Synthetic"). The screenshots were taken just before the copy switched from US F-1 to UK pre-CAS (headline, interview title, GBP figures); the layouts are unchanged. If you can only take a few images, the most important are `01-home-desktop`, `01-home-phone-part1`, `03-facts-and-funding-desktop`, `04-interview-picker-phone`, `05-voice-interview-live-phone` and `06-scorecard-desktop`.

## 7. Constraints you must respect

**Trust and legal (non-negotiable):**
- The interviewer is always presented as a **fictional AI**, never a real officer, embassy, UKVI or university. **No government branding:** no flags, seals or eagles, and no "official" look.
- Never imply a visa outcome or chance of success. No "pass rate", no "guaranteed", no approval meter.
- Keep a short disclaimer visible on the home page, the interview screen and the feedback page. You may restyle and shorten it, but not remove it.
- Feedback must not rate honesty, nervousness, confidence or emotion. Don't suggest a "confidence score".
- Before the first session, students must be told which vendors receive their voice and facts (ElevenLabs for voice; HeyGen for video). You can redesign how this is shown (e.g. a one-time consent step instead of repeating it on every card).

**Technical:**
- Next.js 16 (App Router), React 19, TypeScript, plain CSS with variables. Suggest CSS and React changes, not a new framework or UI kit.
- **Phone-first and light:**
  - no heavy images, video backgrounds or large animation libraries;
  - inline SVG illustrations are fine;
  - respect `prefers-reduced-motion`.
- Must work in Android Chrome and iOS Safari. The microphone permission prompt must follow a tap.
- Accessibility: WCAG AA contrast, keyboard focus visible, real buttons and labels.

**Brand:** the name "Interview Practice" is a placeholder. Suggestions for a name, logo idea or tone are welcome but optional. The sun-and-mountain motif is a gentle nod to Nepal; keep it subtle and not touristy.

## 8. What we already think is weak (please confirm, reject or go further)

**Overall:**
1. **Two different products.** The home page is designed; the inner pages (facts, interview, results) look like plain documents. They have no header, no logo, no way back home, no step indicator and different widths.
2. **No sense of progress.** The journey is Pick → Check facts → Talk → Feedback, but the inner pages don't show where you are.
3. **The coral-red accent is used for everything:** buttons, links, labels, selected cards, quotes. Errors and the End button are also red, so "brand" and "danger" blur together.
4. **Font choice.** Nunito is friendly but may feel less "elegant / premium" than wanted. Is a different pairing better (e.g. a refined serif or neutral sans for headings)?

**Home:**
5. The hero is good, but is the message specific enough ("visa *and* university interviews")? Is the illustration clear or decorative noise?
6. Four feature cards plus four steps plus two choice cards may be too much scrolling before sign-in on a phone. Should sign-in come sooner?
7. No social proof, FAQ or "what you get" preview (e.g. a mini scorecard). Would one help trust?

**Facts page:**
8. Shows raw keys like `funding.costs` and ISO dates like `2027-08-23`.
9. ~13 facts in one long list with no grouping (About you / Programme / Costs / Funds).
10. "Save a new version" is jargon.
11. The funding table is useful, but its caveat text is dense.

**Interview picker:**
12. Labels like "Video interviewer A" mean nothing to a student.
13. Each option is a paragraph of vendor and data-use text.
14. On desktop, ~70% of the screen is empty.

**Live voice:**
15. The status appears twice (inside the panel and below it).
16. The dark translucent overlay chips look heavy on the warm panel.

**Feedback page:**
17. Status pills show internal words ("completed", "deadline").
18. "Based on: cost-tuition, cost-living…" shows internal IDs.
19. Student quotes are styled as underlined red links, which looks like an error.
20. The rating form is long and visually heavy, and the disabled Submit button looks washed out.
21. There's no summary at the top (e.g. "1 strength, 1 thing to practise") and no clear "Practise again" button.

## 9. Response format (please follow)

**A. Five-second test.** Looking only at `01-home-phone.png`, what do you think this service is, who is it for, and what would you tap first? Then: what's unclear?

**B. Overall direction.** In 5–8 sentences, the visual direction you recommend (mood, colour, type, density, illustration style). Then give **two alternative directions** in 2–3 sentences each, so the owner can choose.

**C. Design system proposal.** Concrete values:
- **Colours:** a palette with hex values. Show which colour is for brand, interactive, success, warning, danger and neutral, and check text contrast.
- **Type:** font pairing (free Google Fonts), with a type scale (sizes, weights, line heights) for display, h1, h2, h3, body, small and label.
- **Spacing and shape:** spacing scale, radii, shadows and max content widths.
- **Components:** button, card, pill/tag, input, radio card and the page header/stepper, with states.

**D. Screen-by-screen review.** For **each** screen in section 4 (home, sign-in, facts, interview picker, live voice, live video, feedback, rating), give:
- **Keep:** what works.
- **Problems:** numbered, each tagged **High / Medium / Low** impact.
- **Redesign:** the layout you'd use, top to bottom. Mention phone first, then desktop changes. Include exact copy where copy is the problem.
- **Optional:** a rough ASCII wireframe for the phone layout.

**E. Journey and information architecture.** Should the order or number of steps change (e.g. a consent step, merging facts into a stepper, where sign-in sits)? What should signed-in students see on `/`?

**F. Copy.** Rewrite the key lines in plain, warm English for a nervous non-native speaker:
- hero headline and subline;
- the four feature titles;
- choice card titles and descriptions;
- the facts-page intro;
- the interview disclaimer;
- the feedback-page intro;
- the empty / no-transcript message.

Keep the legal meaning of disclaimers.

**G. Trust and delight.** 3–5 small touches that make it feel safe and joyful without being childish (micro-copy, empty states, a celebration after a session, etc.). Respect section 7.

**H. Accessibility and mobile issues** you can see in the screenshots: contrast, tap target sizes, focus and motion.

**I. Top 10 changes, ranked.** Rank by impact divided by effort. Give each change one line: what to change, on which screen, impact (H/M/L) and effort (S/M/L).

**J. Questions for the owner:** anything you'd need to know to go further.

Be direct. If something looks amateur, say so and say why. We would rather hear hard truths now than after students see it.
