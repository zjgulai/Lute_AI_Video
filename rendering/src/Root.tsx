import { Composition } from "remotion";
import { VideoComposition } from "./VideoComposition";

// Load pipeline data — in production this comes from the Python pipeline output
// For Remotion Studio dev, we use a sample JSON
const sampleData = {
  script_id: "SAMPLE",
  total_duration: 45,
  shots: [
    {
      id: 1,
      start_time: 0,
      end_time: 3,
      text_overlay: "Pumping at work?",
      voiceover: "Pumping at work shouldn't feel like hiding in a bathroom stall.",
      visual: "Split screen: frustrated woman vs bathroom door",
    },
    {
      id: 2,
      start_time: 3,
      end_time: 8,
      text_overlay: "3x a day. 20 min each.",
      voiceover: "3 times a day. 20 minutes each. In a supply closet.",
      visual: "Woman checking watch at desk",
    },
    {
      id: 3,
      start_time: 8,
      end_time: 20,
      text_overlay: "100% hands-free",
      voiceover: "The X1 fits in your bra. Silent. Nobody knows you're pumping.",
      visual: "Product demo: wearing pump under blouse",
    },
    {
      id: 4,
      start_time: 20,
      end_time: 35,
      text_overlay: "FDA Cleared | 280mmHg",
      voiceover: "Hospital-grade suction. FDA cleared. 2.5 hour battery.",
      visual: "Product close-up with specs overlay",
    },
    {
      id: 5,
      start_time: 35,
      end_time: 45,
      text_overlay: "Shop Now ↑",
      voiceover: "Freedom to feed, wherever you are. Link in bio.",
      visual: "Product in use, warm lighting",
    },
  ],
  captions: [
    { start_time: 0, end_time: 1.2, text: "Pumping at work" },
    { start_time: 1.2, end_time: 3, text: "shouldn't feel like" },
    { start_time: 3, end_time: 5, text: "3 times a day." },
    { start_time: 5, end_time: 8, text: "In a supply closet." },
    { start_time: 8, end_time: 12, text: "The X1 fits in your bra." },
    { start_time: 12, end_time: 16, text: "Silent." },
    { start_time: 16, end_time: 20, text: "Nobody knows." },
    { start_time: 20, end_time: 25, text: "Hospital-grade suction." },
    { start_time: 25, end_time: 30, text: "FDA cleared." },
    { start_time: 30, end_time: 35, text: "2.5 hour battery." },
    { start_time: 35, end_time: 40, text: "Freedom to feed," },
    { start_time: 40, end_time: 45, text: "wherever you are." },
  ],
};

const fps = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ShortVideo"
        component={VideoComposition}
        durationInFrames={Math.ceil(45 * fps)}
        fps={fps}
        width={1080}
        height={1920}
        defaultProps={{
          data: { ...sampleData, brand_name: "@BrandName" },
          audioSrc: null,
          backgroundColor: "#FFF5F7",
          primaryColor: "#FF6B9D",
          textColor: "#2D3436",
        }}
      />
    </>
  );
};
