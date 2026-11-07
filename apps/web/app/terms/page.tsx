// Plain-language terms of use.

import type { Metadata } from "next";
import Shell from "@/components/Shell";
import { CONTACT_EMAIL, DISCLAIMER } from "@/lib/copy";

export const metadata: Metadata = { title: "Terms · Interview Practice" };

export default function Terms() {
  return (
    <Shell title="Terms" intro="Last updated 6 November 2026">
      <div className="legal">
        <p>By creating an account or using Interview Practice at nepali.global, you agree to these terms.</p>

        <h2>This is practice only</h2>
        <p>{DISCLAIMER}</p>
        <ul>
          <li>It doesn&apos;t guarantee any result in a real interview, or any CAS or visa.</li>
          <li>It isn&apos;t immigration, legal or financial advice. For decisions about your application, ask your university or a qualified adviser.</li>
          <li>The real interview may be longer and different. Your university&apos;s own instructions always come first.</li>
          <li>Never use this service during a real interview.</li>
        </ul>

        <h2>AI can be wrong</h2>
        <p>The interviewer is an AI and can make mistakes or say things that aren&apos;t accurate. Please check anything important yourself.</p>

        <h2>Your account</h2>
        <ul>
          <li>You must be 18 or over.</li>
          <li>Give truthful account details and keep your password private.</li>
          <li>Please use one account per person. Don&apos;t create more accounts to get more free time.</li>
        </ul>

        <h2>Using the service fairly</h2>
        <p>
          Don&apos;t misuse the service, try to break it or get around its limits, copy it in bulk, or use it to make up a
          story for a real application. We can suspend or close an account that does.
        </p>

        <h2>Free time and codes</h2>
        <p>
          Free sessions and promo codes have limits and can expire. They have no cash value. We may change or end the
          free plan at any time. There are no paid plans yet.
        </p>

        <h2>Changes and availability</h2>
        <p>
          This is an early version. Features may change, and calls may fail or be unavailable. We provide the service
          as it is, without promises that it will always work.
        </p>

        <h2>Our responsibility</h2>
        <p>
          As far as the law allows, we aren&apos;t responsible for any decision made by a university or government, or for
          losses that come from using or relying on this service.
        </p>

        <h2>Your privacy</h2>
        <p>Our <a href="/privacy">Privacy Policy</a> explains what happens to your information, including your voice.</p>

        <h2>Changes to these terms</h2>
        <p>If we change these terms, we&apos;ll update this page and its date. Using the service after that means you accept the new terms.</p>

        <h2>Contact</h2>
        <p>{CONTACT_EMAIL || "Contact email to be added."}</p>
      </div>
    </Shell>
  );
}
