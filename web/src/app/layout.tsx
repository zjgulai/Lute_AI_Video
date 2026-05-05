import type { Metadata } from "next";
import "./globals.css";
import { I18nProvider } from "@/i18n/I18nProvider";

export const metadata: Metadata = {
  title: "Short Video Factory — AI Multi-platform Distribution",
  description: "16-step AI review pipeline · Employee IP + Influencer Content · Multi-platform distribution to Shopify/Amazon/TikTok/Reddit",
};

export const viewport = "width=device-width, initial-scale=1";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="light">
      <body className="antialiased">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
