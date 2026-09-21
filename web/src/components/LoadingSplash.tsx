import preloadVideo from "../video/preload.mp4";

/**
 * The dashboard's own loading state, wherever it needs one: the apex waiting
 * for a session to redirect on, and the dashboard host waiting for auth to
 * resolve before it can pick /login vs /projects. Complements `BootSplash`
 * (main.tsx), which covers the very first paint of any page including the
 * landing - this one is for waits that happen *after* that, if auth takes
 * longer to resolve than the boot splash stayed up for. Loops, unlike
 * `BootSplash`'s single play-through, because there is no "ended" event to
 * hang a dismissal on here - `loading` flipping to `false` is what ends it.
 *
 * `muted` is load-bearing, not a style choice: unmuted autoplay is blocked by
 * every major browser, so a plain `autoPlay` without it would just render the
 * video's first frame and never move. Deliberately still muted even though
 * `BootSplash` now tries for sound - this one loops for as long as auth takes,
 * which is unpredictable, and looping audio under an open-ended wait reads as
 * a malfunction rather than a brand moment.
 */
export function LoadingSplash({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg" role="status" aria-live="polite">
      <video
        src={preloadVideo}
        autoPlay
        muted
        loop
        playsInline
        onLoadedMetadata={(e) => {
          e.currentTarget.playbackRate = 1.5;
        }}
        className="w-40 max-w-[40vw] sm:w-48"
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}
