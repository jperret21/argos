# Live Preview Chain

The live preview processes frames through three stages: camera download → off-thread
processing → UI display. Each stage runs on its own thread so the UI never freezes.

```{graphviz} preview_chain.dot
:align: center
```

## Data flow

1. **ExposureWorker** (QThread) starts the camera exposure via Alpaca HTTP, polls
   `ImageReady`, and downloads the raw uint16 array.
2. **PreviewProcessor** (QThread) receives the raw array via the `frame_ready` signal
   and computes the display render, star field, frame metrics, and histograms — all
   off the UI thread.
3. The **UI thread** receives a `ProcessedFrame` dataclass and applies the final
   display stretch, overlays, and histogram update. These are cheap enough
   (numpy uint8 → QImage) to run on the main thread.

## Latest-frame-wins

If frames arrive faster than `PreviewProcessor` can process them, stale jobs are
silently dropped. The processor keeps only the most recently submitted `(raw, view)`
and skips any intermediate ones.
