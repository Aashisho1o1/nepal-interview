// Plain-language privacy policy. Describe only what the app really does: update this page
// before changing what is collected or who receives it.

import type { Metadata } from "next";
import Shell from "@/components/Shell";
import { CONTACT_EMAIL } from "@/lib/copy";

export const metadata: Metadata = { title: "Privacy Policy · Victoria" };

export default function Privacy() {
  return (
    <Shell title="Privacy Policy" intro="Last updated 6 November 2026">
      <div className="legal">
        <p>
          Victoria at nepali.global is run by a small team. This page explains what we collect when you use
          it and what we do with it.
        </p>

        <h2>What we collect</h2>
        <ul>
          <li><strong>Your account:</strong> your name, your email and a scrambled version of your password. We can&apos;t read your password.</li>
          <li><strong>Details you choose to add:</strong> such as your university, course, family income, savings and loans. All of these are optional.</li>
          <li><strong>Your practice sessions:</strong> when each one started and ended, whether it was video or voice, and how much free time it used.</li>
          <li><strong>Your ratings:</strong> your answers and any comment you leave after a session.</li>
          <li><strong>Technical data:</strong> your network address, which we use to limit abuse such as repeated sign-ups. Our hosting providers may also log it.</li>
        </ul>

        <h2>Your voice</h2>
        <p>
          Your interviewer is run by AI services from other companies, so what you say on a call is sent to them while
          the call is running. These services may keep recordings or transcripts under their own terms.
        </p>
        <ul>
          <li><strong>Voice calls:</strong> these services also receive your name and the details you added, so the interviewer can ask about them.</li>
          <li><strong>Video calls:</strong> they receive anything you say out loud. Some video interviewers also receive your name and the details you added; the practice page says which before you start.</li>
        </ul>
        <p>We don&apos;t store recordings or written transcripts of your calls ourselves.</p>
        <p>Please don&apos;t say or type anything you don&apos;t want shared with these services, such as passport or bank account numbers.</p>

        <h2>How we use it</h2>
        <ul>
          <li>To run your account and your practice sessions.</li>
          <li>To count your free time and stop misuse.</li>
          <li>To improve the practice. Our small team can see your account email, the details you added, your sessions and your ratings.</li>
        </ul>
        <p>We don&apos;t sell your information, and we don&apos;t use it for advertising.</p>

        <h2>Who else receives it</h2>
        <p>
          Only the AI services described above and the companies that host our website and database. Some of them may
          process your information outside Nepal. We may also share information if the law requires it.
        </p>
        <p>The waiting list is a separate Google Form, so Google handles what you enter there.</p>

        <h2>Cookies</h2>
        <p>
          We use one cookie, which keeps you signed in. We don&apos;t use advertising or analytics cookies. Your browser
          also briefly remembers a code that stops a session starting twice.
        </p>

        <h2>How long we keep it</h2>
        <p>We keep your account and session records until you ask us to delete them. Nothing is deleted automatically yet.</p>

        <h2>Your choices</h2>
        <ul>
          <li>You can skip the optional details, or change them at any time on the About you page.</li>
          <li>You can email us to ask for a copy of your information, to correct it, or to delete your account and records. We&apos;ll reply within 30 days.</li>
        </ul>
        <p>We can&apos;t delete what other companies have already received, but we can tell you how to ask them.</p>

        <h2>Age</h2>
        <p>This service is for people aged 18 or over.</p>

        <h2>Changes</h2>
        <p>If we change this policy, we&apos;ll update this page and its date.</p>

        <h2>Contact</h2>
        <p>{CONTACT_EMAIL || "Contact email to be added."}</p>
      </div>
    </Shell>
  );
}
