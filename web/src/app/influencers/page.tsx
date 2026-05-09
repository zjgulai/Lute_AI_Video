import { redirect } from "next/navigation";

export default function InfluencersRedirect() {
  redirect("/library?tab=influencers");
}
