import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  interpolate,
  spring,
  Sequence,
  Audio,
  Video,
} from "remotion";

interface Transition {
  from_clip: number;
  to_clip: number;
  type: "clean" | "match_cut" | "action_cut" | "soft_crossfade";
  duration_frames: number;
  description?: string;
}

interface Shot {
  id: number;
  start_time: number;
  end_time: number;
  text_overlay?: string;
  voiceover?: string;
  visual?: string;
  videoSrc?: string;
  transition?: Transition;
}

interface Caption {
  start_time: number;
  end_time: number;
  text: string;
}

interface VideoCompositionProps {
  data: {
    script_id: string;
    total_duration: number;
    shots: Shot[];
    captions?: Caption[];
    transitions?: Transition[];
    brand_name?: string;
  };
  audioSrc: string | null;
  backgroundColor: string;
  primaryColor: string;
  textColor: string;
}

const fps = 30;

const ShotSegment: React.FC<{
  shot: Shot;
  isActive: boolean;
  primaryColor: string;
  textColor: string;
}> = ({ shot, isActive, primaryColor, textColor }) => {
  const frame = useCurrentFrame();
  const shotStartFrame = shot.start_time * fps;
  const shotDurationFrames = (shot.end_time - shot.start_time) * fps;
  const localFrame = frame - shotStartFrame;
  const fadeFrames =
    shot.transition?.type === "soft_crossfade"
      ? shot.transition.duration_frames
      : 0;
  const fadeStartFrame = Math.max(0, shotDurationFrames - fadeFrames);
  const fadeOut =
    fadeFrames > 0 && shotDurationFrames > 0
      ? interpolate(localFrame, [fadeStartFrame, shotDurationFrames], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;

  // Entrance animation
  const entrance = spring({
    frame: localFrame,
    fps,
    config: { damping: 20, stiffness: 200 },
    durationInFrames: 15,
  });

  // Subtle zoom for dynamism (TikTok algorithm prefers movement)
  const zoom = interpolate(localFrame, [0, shotDurationFrames], [1, 1.05], {
    extrapolateRight: "clamp",
  });

  if (!isActive || localFrame < 0 || localFrame > shotDurationFrames) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        transform: `scale(${zoom})`,
        opacity: fadeOut,
        backgroundColor: "#FFF5F7",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Video asset — if available, render the actual clip */}
      {shot.videoSrc ? (
        <Video
          src={shot.videoSrc}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      ) : (
        /* Placeholder visual — when no video asset is available */
        <div
          style={{
            width: "80%",
            height: "60%",
            backgroundColor: "#FFE4EC",
            borderRadius: 20,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            opacity: entrance,
          }}
        >
          <p
            style={{
              color: "#FF6B9D",
              fontSize: 24,
              fontWeight: 500,
              textAlign: "center",
              padding: 20,
            }}
          >
            {shot.visual || `Shot ${shot.id}`}
          </p>
        </div>
      )}

      {/* Text overlay */}
      {shot.text_overlay && (
        <div
          style={{
            position: "absolute",
            bottom: 280,
            left: 0,
            right: 0,
            textAlign: "center",
            opacity: entrance,
          }}
        >
          <span
            style={{
              backgroundColor: primaryColor,
              color: "white",
              padding: "12px 28px",
              borderRadius: 30,
              fontSize: 36,
              fontWeight: 700,
              fontFamily: "system-ui, sans-serif",
            }}
          >
            {shot.text_overlay}
          </span>
        </div>
      )}
    </AbsoluteFill>
  );
};

const CaptionOverlay: React.FC<{
  captions: Caption[];
  textColor: string;
}> = ({ captions, textColor }) => {
  const frame = useCurrentFrame();
  const currentTime = frame / fps;

  // Find active caption
  const activeCaption = captions.find(
    (c) => currentTime >= c.start_time && currentTime < c.end_time
  );

  if (!activeCaption) return null;

  const captionDuration = activeCaption.end_time - activeCaption.start_time;
  const localTime = currentTime - activeCaption.start_time;
  const entrance = spring({
    frame: localTime * fps,
    fps,
    config: { damping: 15, stiffness: 180 },
    durationInFrames: Math.min(8, captionDuration * fps * 0.3),
  });

  return (
    <div
      style={{
        position: "absolute",
        bottom: 120,
        left: 0,
        right: 0,
        textAlign: "center",
      }}
    >
      <span
        style={{
          color: "white",
          fontSize: 52,
          fontWeight: 800,
          fontFamily: "system-ui, sans-serif",
          textShadow: "2px 2px 8px rgba(0,0,0,0.6), 0 0 20px rgba(0,0,0,0.4)",
          opacity: entrance,
          display: "inline-block",
          padding: "8px 24px",
          borderRadius: 12,
          backgroundColor: "rgba(0,0,0,0.4)",
        }}
      >
        {activeCaption.text}
      </span>
    </div>
  );
};

export const VideoComposition: React.FC<Record<string, unknown>> = (props) => {
  const {
    data,
    audioSrc,
    backgroundColor,
    primaryColor,
    textColor,
  } = props as unknown as VideoCompositionProps;
  const frame = useCurrentFrame();
  const currentTime = frame / fps;

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* Render each shot */}
      {data.shots.map((shot, index) => {
        const transition = data.transitions?.find(
          (item) => item.from_clip === index + 1
        );
        const shotWithTransition = { ...shot, transition };

        return (
          <Sequence
            key={shot.id}
            from={Math.floor(shot.start_time * fps)}
            durationInFrames={Math.ceil((shot.end_time - shot.start_time) * fps)}
          >
            <ShotSegment
              shot={shotWithTransition}
              isActive={
                currentTime >= shot.start_time && currentTime < shot.end_time
              }
              primaryColor={primaryColor}
              textColor={textColor}
            />
          </Sequence>
        );
      })}

      {/* Caption overlay */}
      {data.captions && data.captions.length > 0 && (
        <CaptionOverlay captions={data.captions} textColor={textColor} />
      )}

      {/* Audio track */}
      {audioSrc && <Audio src={audioSrc} />}

      {/* Brand watermark */}
      {data.brand_name && (
        <div
          style={{
            position: "absolute",
            top: 30,
            right: 30,
            color: "rgba(255,255,255,0.6)",
            fontSize: 20,
            fontWeight: 600,
          }}
        >
          {data.brand_name}
        </div>
      )}
    </AbsoluteFill>
  );
};
