import { redirect } from "next/navigation";

export default function BrandPackagesRedirect() {
  redirect("/library?tab=brand_kit");
}
