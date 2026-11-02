import type { Metadata, Viewport } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";

const nunito = Nunito({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "Interview Practice",
  description: "Practise your UK pre-CAS interview with a friendly, fictional AI interviewer.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#fffaf3",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={nunito.variable} data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
