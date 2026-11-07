# Public launch design brief: UK pre-CAS interview practice for Nepali students

Prepared 2026-11-06 from the live site, the source code and web research. You are reviewing a real product that is about to be promoted publicly. The founder wants the frontend to be much stronger, more convincing and more tempting to try, without saying anything untrue.

**Changes made after this brief was written.** Treat these as done, even where a later section or a screenshot shows the old state:

- The feedback promises are gone. The lead no longer mentions feedback, "How it works" has three steps, and "What you get" and the green tick are removed. The Practise notice is removed. Step 4 is now "Rate it", and the after-call page is titled "Your session" and thanks the student before the rating form. Written feedback may return later, so please still answer for both cases.
- The "add your details" prompt now shows only for a card that uses them. The About you page says the video interviewer doesn't receive them.
- Each card now shows its own data note.
- Simple Privacy and Terms pages exist, linked from every page and from sign-up. They await legal review. Items B1 and A1 to A4 in section 6 are therefore addressed, apart from account deletion, which is by email.

How to read the evidence in this brief:

- **Verified** means read directly in the code, on the live site or in the cited source.
- **Inference** means a judgement that has not been tested with real students.
- No user research or conversion data exists yet. Please do not treat any recommendation here as proven.

## 1. Your job

Act as a senior product designer and conversion copywriter who is also honest about evidence. Review everything below, attack the assumptions, and produce the deliverables in section 11.

Screenshots are attached separately and listed in section 12. If they are not attached, ask for them before giving visual judgements. No live-call image exists, so mark during-call visual advice as provisional.

Please challenge the founder's clip idea and the recommendations in this brief. Disagreement is useful. Do not invent statistics, testimonials, user counts or success rates.

## 2. The product

**What it is.** A web app at https://www.nepali.global where a student speaks out loud with a fictional AI interviewer called Officer Miller, on a real-time video call or a voice-only call.

**Who it is for.** Nepali students who hold a UK university offer and must pass that university's pre-CAS interview. A CAS is the document a university issues so the student can apply for a UK student visa.

**The session.** Two minutes and three questions in spoken English, personalised when the interviewer has the student's details. The interviewer does not coach during the call.

**Stage.** Early access, founder testing reactions. The founder has confirmed a Video A call works in production. Paid packages are not built; a Google Form collects a waiting list.

**Free plan as shown on the site.** A voice session every day, plus a video session on each of the first three days. In the code these are Nepal calendar days counting the sign-up day, and unused sessions expire at midnight. Shared promo codes can add more.

**The flow.**

1. Home page, create an account (name, email, password).
2. About you: five optional details, an optional full bio, or skip.
3. Practise: choose a card, start, talk for two minutes.
4. After-call page: written feedback was designed for this page, but see section 6.

## 3. Audience evidence

Research findings, with sources. The evidence on trust and discovery is thin.

**The interview itself (verified from university guidance)**

- There are two separate interviews. The university runs pre-CAS. The Home Office may run its own credibility interview. Passing the first does not exempt a student from the second ([Bournemouth](https://intranetsp.bournemouth.ac.uk/policy/Pre-CAS-Interview-Guidance-Information.pdf)).
- Nepal is named directly by universities. [Greenwich](https://www.gre.ac.uk/__data/assets/pdf_file/0018/412245/university-of-greenwich-credibility-interview-guidance-1.pdf) requires Nepali students to pass, and [LJMU](https://cd-prod.ljmu.ac.uk/discover/student-support/international-student-support/study-visas/pre-cas-interviews) lists Nepal.
- Formats vary. LJMU is self-recorded and takes 20 to 25 minutes. [Coventry](https://www.coventry.ac.uk/student-central/cuc/before-you-start/credibility-interviews/) is live and takes about 45 minutes. This product's two minutes is a short drill, so "full mock interview" would be false.
- Stakes: a fail means no CAS at Coventry. LJMU requires at least £1,000 paid before recording, allows one resit for borderline cases, then rejects.
- Scripted answers are dangerous. Greenwich says a student seen reading a script will likely fail. Bournemouth bars agents from giving model answers, rehearsing specific responses, coaching or rehearsing interviews. That rule is addressed to agents and does not mention software. [UWE](https://www.uwe.ac.uk/courses/international-study/visas/applying/pre-cas-interviews) warns against prepared answers and requires students to confirm they are not using generative AI during the interview. Coventry recommends practice interviews, specifically talking answers through with an agent, family or friends; it says nothing about AI tools.

**Market size and timing (researcher's totals from the [Home Office dataset](https://assets.publishing.service.gov.uk/media/6a85c3741b45e4e555421eda/entry-clearance-visa-outcomes-datasets-jun-2026.xlsx), main applicants, sponsored study)**

| Measure | Figure |
|---|---|
| Nepali visas issued, year ending June 2026 | 16,300 |
| Refused, same period | 691, about 4.1% of issued plus refused |
| Issued, Q1-Q2 2026 against Q1-Q2 2025 | 5,771 against 8,964, down 36% |
| Q3 share of 2025 grants | 42% |

Inferences from this table, whose 2026 figures are provisional: demand fell in the first half of 2026 from a 2025 record. Visa decisions peak in Q3, with pre-CAS interviews earlier. Refusal is a minority outcome among students who already hold a CAS, but it is unstable: 4.1% in the latest year, 7.2% the year before, and 2.7% to 15.8% by quarter. Fear-based "visa refused" copy could overstate the risk. The sharper worry may be losing a CAS after paying a deposit. We found no published pre-CAS fail rate.

**Trust.** Regulators have accused some Nepali education consultancies of fraud and misleading students. [The PIE](https://thepienews.com/nepalese-education-consultancies-protest-sweeping-new-regulations/) reports fraud raids and allegations of visa guarantees, fabricated offer letters and refused refunds. New rules arrived in July 2026. Whether students distrust consultancies has not been measured. Success-rate claims could make this product look like the same behaviour (inference).

**Devices and data.** Android is 78% of mobile use ([StatCounter](https://gs.statcounter.com/os-market-share/mobile/nepal), October 2026). [One source](https://pulse.internetsociety.org/en/reports/NP/) shows 14 Mbps mobile against 88 Mbps fixed from a small sample, and [Kathmandu Post](https://kathmandupost.com/science-technology/2026/04/14/4g-keeps-growing-fast-in-nepal-while-users-still-face-slow-speeds-and-patchy-coverage) reports common slow-speed complaints outside cities. Unreliable loading looks like a bigger risk than data cost (inference).

**Discovery channels.** Facebook has [14.8M ad reach](https://datareportal.com/reports/digital-2026-nepal). TikTok staff describe exam preparation as a content category in Nepal ([B360](https://www.b360nepal.com/detail/27431/tiktok-emerges-as-key-learning-and-discovery-tool-in-nepal)); there is no independent usage data. Word of mouth is untested here. We found no survey of student fears or AI trust.

**AI practice evidence is weak.** A small qualitative preprint on [20 US computing students](https://arxiv.org/pdf/2506.16542) doing AI mock coding interviews found that many described feeling more confident; it did not measure outcomes. We found nothing specific to Nepali students.

**Direct alternatives (pages read; none showed a demo video)**

| Product | Price | Try without an account | Proof shown |
|---|---|---|---|
| [PreCAS Training](https://globaluniprep.com/) | 1 free mock; NRs 999 for 10; NRs 2,000 live | One answer of up to 30 seconds | None |
| [finduni.ai](https://finduni.ai/guides/pre-cas-vs-ukvi-interview) | From NPR 199 | 4 questions by voice | ["400+" questions](https://finduni.ai/uk-credibility-mock-interview) |
| [House of Admissions](https://houseofadmissions.com/study-in-uk/visas/ukvi-interview/) | Free | A self-timed question tool that records nothing | "99% visa success", self-reported |
| [PrepEx](https://prepex.ai/ai-pre-cas-interview) | Credits, price unstated | No | None |
| [EEC](https://eecglobal.com/ai/ukprecas) (India) | "100% free" | Not stated | "98%", unsourced |

Some consultancies give mock practice free as part of their admissions service (House of Admissions, EEC), so free human practice is part of the competition. Inference: a clip would be unusual among these five. Two of them (PreCAS Training, finduni.ai) capture a spoken answer before sign-up, while this product requires an account first.

## 4. Non-negotiable constraints

1. **Never name the technology vendors anywhere in the product or in your copy.** The founder is cautious about competitors copying fast. Write "AI interviewer".
2. **No guarantees or predictions.** Never say or imply "pass", "approved", "visa success", a score out of 100, or a chance percentage.
3. **No implied affiliation.** No UKVI, Home Office, GOV.UK or university branding, logos or lookalike styling. Avoid "visa officer". Say the interviewer is a fictional AI. "Officer Miller" is the name used in the call; recommend whether it should appear in marketing, and say why.
4. **No fabricated proof.** No invented testimonials, numbers or university logos.
5. **No model answers.** Universities warn against scripted responses, so the product must not teach memorised lines. Add the idea "practise beforehand, never during your interview" where it fits.
6. **Truthful claims only.** Anything promised must work on the card a free student actually uses.
7. **Lean code.** The founder wants minimal code and no over-engineering. Current frontend: one CSS file and no UI library. Mark each recommendation S, M or L for effort.
8. **Mobile first and light.** Visitors are probably on Android phones with uneven connections (inference from national figures; no analytics exist). No heavy imagery. Autoplaying video is listed in section 7 for comparison only, and you must justify it if you recommend it.
9. **The API stays private.** The browser reaches our API only through the website, which proxies `/api/*`; during a call it also connects directly to outside services for media. Do not propose exposing the API.
10. **No free live call without sign-up yet.** Each call costs real money, sign-up has no email check, and rate limits are per process. Propose it only together with protections. No per-call cost can be shared. Assume each free call matters, and do not base your answer on a number.
11. **Required disclosure.** Somewhere before Start, a student must learn that the interviewer is a fictional AI, that it is unconnected to any university or government, and that their voice goes to AI services. The wording and the repetition may change, subject to legal review.

## 5. The current frontend

**Stack (verified).** Next.js 16, React 19, TypeScript, about 2,400 lines in `apps/web`. One stylesheet, `app/globals.css`. Shared wording (disclaimer, data note, card text) is in `lib/copy.ts`; most page wording is inline in each page. `apps/web/public` does not exist yet. There are no analytics, no Open Graph image, no privacy or terms page, and no Nepali-language copy. Page title: "Interview Practice".

**Design system (verified).** Stated intent in the stylesheet: "Editorial minimal: white canvas, near-black text, hairline borders, one action colour (black). Coral is the logo and line icons only. No gradients, no shadows."

| Token | Value |
|---|---|
| Background, ink | `#ffffff`, `#0b0b0f` |
| Muted text, faint text | `#6e6e73`, `#8e8e93` |
| Hairlines | `#e5e5ea`, `#d2d2d7` |
| Surface | `#f5f5f7` |
| Brand coral (logo, card icons, answer-bubble border); sun (logo only) | `#e4573d`, `#ffc94d` |
| Link | `#0066cc` |
| Good, warning, bad | `#17794f`, `#8a5a00` on `#fff3d6`, `#b3261e` |
| Radii | Tokens 8px, 16px, pill 999px; also hard-coded 12px (inputs, notices) and 20px (voice panel) |
| Page widths | 1080px, 720px, 560px |
| Type | System font stack; 16px body at 1.55; display `clamp(2rem, 6vw, 3rem)`, weight 600, tracking -0.02em; uppercase 12px eyebrows |
| Buttons | Pill, 48px tall on phones, 44px on desktop; primary is black |

Header: a sticky white bar, 56px, with a coral circular logo, the words "Interview Practice", and "Sign in" or "Hi, name / Sign out". The domain is nepali.global, so the brand name and domain do not match. "Interview Practice" began as a placeholder.

### Home page, signed out (`app/page.tsx`)

Single column, 640px (form and waiting-list cards 440px), in this order:

1. Chip: "Student visa interview practice · Early access"
2. H1: "Practise your student interview before the real one."
3. Italic lead: "Practise with an **AI interviewer** on a **video call** or an **audio call**, and get feedback after every session."
4. Small text: "Early access covers the UK pre-CAS interview. The US, Europe and Australia are coming soon."
5. Black button: "Start practising free". It scrolls to the form at the bottom of the page.
6. Static card that imitates a conversation. "Visa interviewer (AI)": "Why did you choose this course?" "Visa applicant (you)": "I chose MSc Data Science because its machine learning modules build on my…" Then a green tick: "✓ Clear and specific".
7. "How it works", four numbered rows:
   - **Create your account.** "Free: a voice session every day, and a video session on each of your first three days."
   - **Tell us about you.** "Five quick details, or skip and practise straight away."
   - **Have a conversation.** "Video or voice. Three questions, out loud, in two minutes."
   - **See your feedback.** "What went well and what to practise, in your own words."
8. "What you get": one example card. Label "Strength", category "Funding explanation", quote "My father will pay the fees from his savings of fifteen thousand pounds, and the deposit is already paid." Then "You named the source and the amount, and both match your confirmed facts." "**Next:** Say when the money will be available, too." Caption: "Example feedback from a practice session."
9. Form card: "Create your free account" with name, email, password (at least 8 characters), and "Free to start. No card needed. Already have an account? Sign in".
10. Card: "Join the waiting list". "We'll let you know when the paid version opens, with more practice time and more countries." The button opens a Google Form.
11. Footer disclaimer: "This is practice only. Your interviewer is a fictional AI, not a university officer or UKVI, and not connected to any university or government. Practising here cannot predict or affect any CAS or visa decision."

Signed in, the hero becomes "Welcome back, name." with "Ready to practise?", "Practise now", "Update my details" and a last-session line. "How it works" and "What you get" still appear beneath.

### About you (`app/prepare/page.tsx`), step 2 of 4

A four-part stepper sits on every inner page: Your account, About you, Practise, Feedback. Intro: "Five quick details help your interviewer ask about your plans. All optional: skip any you'd rather not share."

- Quick fields: name, home country, university, course, family's yearly income in NPR.
- A card, "Want a more realistic interview?", opens a full bio: course start month, previous degree, English test, accommodation, tuition, living costs, scholarship, deposit paid, family savings, education loan.
- With the bio, saving shows "Your funding, added up": a sum in GBP, either "short" or "Covered", questions to be ready for, and "Added up from your figures only. A zero difference doesn't mean your funding is enough for a visa."
- A sticky bar offers "Skip, try it now" and "Save and continue".

### Practise (`app/interview/page.tsx`), step 3 of 4

Title: "Ready when you are, name." Intro: "Two minutes, three questions. Keep your answers short and direct, like the real interview."

Radio cards. The founder is comparing video vendors privately. The plan is for students to see two cards: one video card, currently labelled Video A, and Voice only. The founder still has to apply that setting in production.

- **Video A.** "See a friendly face while you talk. Feels closest to the real thing." Small line: "Available for free users". Chips: "Best on Wi-Fi", "1 session left".
- **Voice only.** "Just talk, no camera. Works well even on slower connections." Chips: "Works on mobile data", "1 session left".

Below the cards, in order:

1. Amber notice: "This interviewer doesn't give written feedback yet. Your session still counts, and you can rate it afterwards."
2. "Have a code?" link
3. "Add your details for a more realistic interview."
4. Data note: "Your voice and the details you give are sent to the AI services that run the interviewer. Our small team reads sessions and ratings to improve the practice."
5. The full disclaimer
6. "Start practice" button

### During a call

Only one area changes per card, so the layout is shared.

- **Video A:** a 16:9 video with rounded corners, capped at 62% of the screen height.
- **Voice card:** a grey 4:3 panel with a plain circle. Its border turns green when listening and pulses black when speaking.
- **Overlay chips:** "Fictional AI · Practice" and a countdown.
- **Status:** the Start button reads "Starting…", then a status line under the video shows "Connecting…", "Your turn. Speak now." or "Interviewer speaking…".
- **Also under the video:** the disclaimer again, and a red "End session" button.

There is no explanation before the browser asks for the microphone. A refused microphone flashes "Allow the microphone to practise." and then moves to the "Your feedback" page, which says "This session didn't start (could not connect), so no time was used." and never mentions the microphone. No screenshot of a live call is attached.

The opening line in the repo's copy of the prompt: "Hello {first name}, I'm Officer Miller, a fictional practice interviewer. This is a practice pre-CAS interview, not a real university or visa interview, and it will take about two minutes, so keep your answers short and direct. Let's begin: why did you choose your course?" Video A sends no name, so there it should begin "Hello there". The live text is pasted into a vendor dashboard by hand, so a recording is the final check.

### After the call (`app/sessions/[id]/page.tsx`), step 4 of 4

What a student sees today is in section 6. A rating form follows: "How did it feel?" with realism 1 to 5, reply speed, could you hear clearly, would you practise again, and an optional comment.

A finished feedback design exists, shown in the sample screenshot with invented data:

- Counts of strengths, items to practise, and items to check
- Sections: "What went well", "Practise next", "Check your documents"
- Each point quotes the student's own words, explains, and gives a "Next" step
- "Before next time", "Not yet confirmed", and a collapsible full transcript

The sample has no items for "Check your documents" or "Not yet confirmed", so those two sections are not visible in it.

## 6. Audit: what is wrong today

### A. Promises the product does not keep (verified; fix before any promotion)

1. **Written feedback does not exist in production for any card.**
   - The home page promises it in the lead ("feedback after every session"), step 4, "What you get" and, when signed in, the "See feedback →" link.
   - The interviewer's closing line says feedback will follow, and the page title says "Your feedback".
   - In reality every provider has `transcripts: false`, no route receives transcripts, and so the grader never runs.
   - A student sees the amber notice before the call. Afterwards they see "This session has no transcript, so we couldn't build written feedback for it."
   - The grading, storage and report screen all exist. What is missing is the route that receives transcripts, turning on each card's `transcripts` setting, and a quality check on the grader.
   - The founder's decision is pending: build it, or change the words. This is the largest issue on the site.
2. **The built-in rules grader contradicts the home page's example.** Given the same sentence, it says "This answer mentioned funding without naming the confirmed source and amount", because it only recognises digits. Even with digits, a student with no saved funding figures is told the amount "does not match any confirmed amount" and is marked for counsellor review. Testing an AI-based grader is required before feedback goes live. The code marks that grader as untested against the live API, and no automated test calls it.
3. **"Add your details for a more realistic interview" is not true on Video A.** Video A deliberately receives none of the student's typed details, by the founder's privacy design. Voice does receive them. The prompt still appears when Video A is selected, and the About you page makes the same promise. The data note also says details are sent, which is not true of typed details on Video A.
4. **Contradictory lines on the after-call page.** When the time runs out it says "This session has no transcript…" and then "Time ran out. The feedback covers the part you completed."
5. **"Student visa interview practice" misdescribes the product.** Pre-CAS is a university interview, not the visa interview. "Visa interviewer (AI)" has the same problem.
6. **"Feels closest to the real thing"** is an untested claim. A two-minute session is not like a 20 to 45 minute interview.

### B. Launch blockers outside design (verified unless marked)

1. No privacy policy or terms page (`/privacy` and `/terms` return 404), although the site collects voice, income and funding details. No account or data deletion exists. Sign-up has no age check. A lawyer should review these.
2. Sign-up has no email verification, and rate limits are per process. The founder already recorded email verification as a requirement before public promotion. Free video minutes cost real money.
3. No analytics, so nobody can tell whether any change works.
4. Some technical traces of the vendors exist outside the visible page. An engineer is handling this, so it is out of scope for you. Please do not investigate or name the vendors.
5. A vendor's terms may require telling users about that vendor before the interaction, which conflicts with hiding it (inference; needs a lawyer). See constraint 1.
6. Unconfirmed: UK rules on immigration advice and Nepal's 2026 consultancy rules may or may not reach personalised feedback from this site. A lawyer should check.

### C. Persuasion weaknesses (inference; please challenge these)

1. **The site never shows the product.** There is no face, no voice and no real screen. The strongest thing it has is a live AI interviewer, and a visitor only meets it after three steps.
2. **The headline is generic.** "Your student interview" does not say pre-CAS, Nepal or the fear behind it. A student searching for "pre-CAS interview" does not get an instant match.
3. **Weak first impression on phones.** A chip, eight lines of heading and text, and a button come before the fake chat card. The italic lead is hard to read, and bolding three phrases weakens emphasis.
4. **The chat card can look like a chatbot,** when the product's point is speaking out loud under pressure. Its green tick also shows a judgement the live product cannot give yet.
5. **The action is far from the form.** The only button scrolls past several sections to a form at the bottom. Three fields come before any value, while two rivals capture a spoken answer first.
6. **"Video A" means nothing to a student.** It is an internal test label. "Available for free users" implies the other card is not free, and both are.
7. **The Practise page is cluttered.** A choice, a warning, a code link, a details link and two legal paragraphs all come before the Start button. The warning is the most colourful thing on the screen.
8. **The disclaimer repeats** in full on the Practise page, during the call and after it.
9. **The waiting-list card sells a product nobody has tried,** at the moment a visitor is deciding whether to try the free one.
10. **No trust story.** The site says nothing about who built it or why a Nepali student should trust it. The founder has no fake proof to offer, so honesty and specificity must carry this. The founder's background is not in this brief, so mark any founder line as a placeholder for them to fill.
11. **Sharing is weak.** With no Open Graph image and the title "Interview Practice", a link pasted into Facebook or WhatsApp looks empty.
12. **The brand is unfinished.** "Interview Practice" under the domain nepali.global, and "Student visa" or "pre-CAS" depending on the line.
13. **"Early access" and "coming soon" countries** may reduce confidence or may add excitement. Unknown.
14. **"Practice" sits close to what some universities warn against.** Bournemouth bars agents from rehearsing interviews, and universities warn against prepared answers. The rule does not name software, and Coventry recommends practice. The positioning may be safer as getting used to speaking under pressure in your own words, rather than learning answers. A lawyer should review this too.

## 7. The founder's idea: a recorded clip on the home page

**The idea.** Record a real mock interview on the actual site, cut 10 to 15 seconds of the interviewer speaking, and put it on the home page so visitors can click it and feel what the product is like. The founder was inspired by LemonSlice.

**Correction to the inspiration (verified).** [LemonSlice's](https://lemonslice.com) hero is a live call: a portrait with a "Start call" button and call code behind it, over a very small silent loop. Its recordings sit lower on the page, for example a 7.3 second, 0.57 MB clip with audio. So the founder's idea is a cheaper cousin of that hero, and for now the safer one.

**Comparable products (verified on 2026-11-06 at phone size, no calls started)**

| Product | First screen | Hero clip | Time to try |
|---|---|---|---|
| Tavus | Talking person, muted loop | 10 s, 1.8 MB | "Speak with Charlie" button |
| Speak | Muted loop of lesson footage | 32 s, 15.9 MB | "Start Speaking for free" |
| Final Round AI | App screen recording, below the phone fold | 6 s, 2.9 MB | Sign-up, desktop download |
| Praktika | Phone mockup with a correction bubble, no video | None | "Try Praktika now", far down the page, not on the first screen |
| Yoodli | No video | None | Sign-up or sales demo |

We found no independent data comparing a muted loop, a click-to-play clip and a live try. Any choice here is a judgement.

**Options**

| Option | For | Against |
|---|---|---|
| Muted autoplay loop | Motion in the first screen | Without sound it cannot show a voice product, and every visitor downloads it |
| Click-to-play with sound and captions | Shows the voice and face, costs data only when tapped, simple | Needs a tap, and the poster has to earn it |
| Live call with no sign-up | The strongest experience | Costs money per visitor, and is open to abuse until email checks and shared limits exist |

**Current recommendation (please challenge).** Click-to-play with sound, with a poster and captions, placed in the first phone screen in place of the fake chat card, and with the action button directly beside it.

**The script already exists, and this is the strongest finding.** The interviewer's opening line (section 5) is 44 words, roughly 15 to 20 seconds when spoken (an estimate; measure it on a recording).

- It is the right kind of monologue, though it may run past the founder's 10 to 15 second target. Say whether to keep it whole or cut it, within the honesty rules below.
- It says "fictional" and "practice" out loud, so the disclosure is part of the demo.
- It needs no real student, so there is no consent issue, and it contains no model answer.
- It ends on a real question: "why did you choose your course?"

**End on that question.** When the clip stops, the viewer has just been asked something and has not answered. Freeze the last frame with the words "Could you answer that out loud? Try it free." and the sign-up action. The unanswered question may do more selling than any headline (inference, untested).

**A later version.** Capture one real exchange showing a probing follow-up, because follow-ups are what scripted answers cannot survive. It needs an invented student and a signed release if a real person speaks, and no answer that could be copied as a model.

**Honesty rules for the clip**

- It must be a real recording of the real product. No re-voicing or separately generated footage.
- Show the real call screen with the "Fictional AI · Practice" chip and the countdown, not just a face.
- Do not cut out the natural delay in a way that misleads about response speed.
- Label it: "Recorded demo. Fictional AI interviewer, not UKVI or a university."
- Before publishing, get the avatar vendor's written confirmation that a recording may be used in marketing, and confirm paid plans cover commercial use.
- A stock avatar face would become visible to every visitor, and stock faces are browsable in vendor libraries. Students are unlikely to recognise it, but a competitor might. A custom avatar avoids this at extra cost.

**Technical specification.** Playback attributes are from [Chrome](https://developer.chrome.com/blog/autoplay), [WebKit](https://webkit.org/blog/6784/new-video-policies-for-ios/) and [Next.js](https://nextjs.org/docs/app/guides/videos). Byte-range is from [Apple's Safari guide](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/CreatingVideoforSafarioniPhone/CreatingVideoforSafarioniPhone.html). Encoding, file naming and hosting are our own judgement.

- On a first visit, sound needs a user gesture such as a tap, so this suits click-to-play. Use `playsinline`, and handle a rejected `play()`.
- `preload="none"` with a small poster and a reserved box, so the video file should not download until tapped (`preload` is only a hint, and the poster still loads) and the layout does not jump.
- Captions in a `<track>` file.
- H.264, yuv420p, `-movflags +faststart`. Target about 2 MB for 15 seconds (a suggested figure, lighter than the three hero clips above; no authoritative budget was found).
- Serve from `apps/web/public` under a versioned filename, and set a long `Cache-Control` through `headers()` in the Next.js config, because `public` files [default to `max-age=0`](https://nextjs.org/docs/app/api-reference/file-conventions/public-folder). Strip file metadata. Test byte-range requests on the host, because iOS needs them.

**Open questions on the clip.** How should the full call screen be framed on a phone? Portrait or 16:9, given Video A's call stage is 16:9? Should captions be English only? Would a poster with a face and a play button get tapped on a slow connection? Is there a better moment to show than the opening?

## 8. Decisions the founder has already made

- Video and voice are chosen on the Practise page, not the home page.
- Student details are optional, and a student can skip straight to practice.
- Video A receives none of the student's typed details, to keep the logic simple and those details away from the video vendor. Voice receives them. On Video A the interviewer asks instead, and spoken answers do reach the video vendor with the audio.
- The session is two minutes, three questions. The code's stated reason is that real pre-CAS answers should be direct.
- Only a waiting list exists for now. No payment system is built.

## 9. What the founder wants a visitor to feel

Convinced, not scared. Roughly: "This is exactly my interview. I can see what it's like. It's free, it takes two minutes, and I want to try it now." The founder is considering asking people to use it publicly, so the page must also be something a student would forward to a friend.

## 10. Questions for you

1. Would you keep the editorial minimal look or change it? It may read as calm and credible, or as cold and unfinished for this audience. Give a specific direction, not a mood.
2. What should the first phone screen contain, exactly?
3. What is the strongest honest value proposition, given two-minute sessions and no feedback unless it gets built?
4. What should the site say if feedback is not ready at launch? Write both versions: feedback live, and feedback not live.
5. How can a site with no testimonials build trust, in a sector where regulators have accused some consultancies of misleading students?
6. Should any marketing copy be in Nepali or Romanised Nepali, given that the interview is in English? Flag any Nepali for native review.
7. Should the product have a real name, and how should it relate to nepali.global? "Nepali" limits it if other countries follow, and the site already mentions them.
8. How should the page speak to fear of losing a CAS without exaggerating?
9. Should the first session start before account creation, once protections exist? Or should sign-up shrink to email only? Remember that each free call costs real money.
10. How should the microphone permission moment and the first 10 seconds of a call be designed, given many first-time users?
11. What should the student see after the call so that they want another go, in both the feedback and no-feedback versions?
12. Are two cards the right choice at all? Or should the page recommend one and offer the other as a fallback, based on connection?
13. What can be shared in Facebook groups and WhatsApp to bring a friend, without paying for ads?

## 11. Deliverables

Be specific enough for an engineer to build without coming back to you.

1. **Verdict.** The five changes most likely to increase visitor-to-first-session, ranked, each with its reasoning, its evidence level and an effort of S, M or L.
2. **New home page, mobile first.** A section-by-section wireframe in text with final copy for every line, and a note on what to remove and why.
3. **Clip decision and storyboard.** Accept, change or reject the recommendation. Give shot, words on screen, duration, poster, end frame and placement.
4. **Practise page rewrite.** Card names, order, what to remove, how to reduce clutter while keeping required disclosure.
5. **During-call and after-call rewrite,** both with and without written feedback.
6. **Visual direction.** Concrete changes to the tokens in section 5: colours, type, spacing, imagery. Use only what fits one CSS file and no heavy assets.
7. **Trust plan** using only true things the founder can do now.
8. **Shareable assets.** Open Graph image concept, page title, description, and a post a student could forward.
9. **Measurement plan.** A small event list: clip played, clip finished, sign-up started, sign-up finished, first call connected, call finished, second session. Include what result would change your mind.
10. **Five-student test.** A script for testing your new design with 5 to 10 real applicants before launch.
11. **What not to do.** Tempting changes that would hurt trust or waste time.

Format: start with the verdict, keep reasoning short, and label every factual claim as sourced or as your own inference.

## 12. Screenshots to attach

Sample data is used on signed-in pages. "Sita" is invented.

| File | What it shows | Source |
|---|---|---|
| `home-fold-mobile.png` | First phone screen | Live site |
| `home-full-mobile.png` | Whole home page, phone | Live site |
| `home-fold-desktop.png` | First desktop screen | Live site |
| `home-full-desktop.png` | Whole home page, desktop | Live site |
| `about-you-mobile.png`, `about-you-desktop.png` | Step 2. The bar over the card is a full-page capture effect; on a real screen it sits at the bottom of the window | Local copy, sample data |
| `practice-mobile.png`, `practice-desktop.png` | Step 3 | Local copy, sample data |
| `after-call-today-mobile.png`, `after-call-today-desktop.png` | Step 4 as students see it today | Local copy, sample data |
| `feedback-design-sample-mobile.png`, `feedback-design-sample-desktop.png` | Feedback design, which is not live | Local copy, invented report |

The grey primary button on the desktop signed-in images is a capture artefact; the real button is black.

Not captured: a live call. Work from the description in section 5. Do not ask for a screenshot showing the avatar's face.
