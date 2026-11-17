import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Victoria: Visa Interview Practice",
  description: "Practise your UK pre-CAS interview out loud with a fictional AI interviewer, on a two-minute video or audio call.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

const OLD_BROWSER = `try{new Function("class A{static{}}")}catch(e){document.addEventListener("DOMContentLoaded",function(){document.body.innerHTML='<p style="padding:24px;font:16px/1.5 sans-serif">This site needs a newer browser. Please update your iPhone to iOS 16.4 or later, or use an Android phone or a computer.</p>'})}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <head>
        {/* The site needs Safari 16.4+ (iOS 16.4). On older phones it would load but do
            nothing, so say why instead. */}
        <script dangerouslySetInnerHTML={{ __html: OLD_BROWSER }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
